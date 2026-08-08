#!/usr/bin/env python3
"""将 Pro600 官方 Rhino COLLADA 网格转换为 Gazebo Ogre2 兼容的二进制 STL。"""

from __future__ import annotations

import argparse
import json
import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


MESH_NAMES = ('base', 'link1', 'link2', 'link3', 'link4', 'link5', 'link6')


def _namespace(root: ET.Element) -> dict[str, str]:
    if not root.tag.startswith('{'):
        raise ValueError('COLLADA 文件缺少 XML namespace。')
    return {'c': root.tag[1:].split('}', 1)[0]}


def _unit_scale(root: ET.Element, namespace: dict[str, str]) -> float:
    unit = root.find('./c:asset/c:unit', namespace)
    return float(unit.get('meter', '1.0')) if unit is not None else 1.0


def _position_sources(
    root: ET.Element,
    namespace: dict[str, str],
) -> dict[str, list[tuple[float, float, float]]]:
    sources: dict[str, list[tuple[float, float, float]]] = {}
    for source in root.findall('.//c:library_geometries/c:geometry/c:mesh/c:source', namespace):
        source_id = source.get('id')
        accessor = source.find('./c:technique_common/c:accessor', namespace)
        if not source_id or accessor is None:
            continue
        params = accessor.findall('./c:param', namespace)
        names = [param.get('name', '').upper() for param in params]
        if names[:3] != ['X', 'Y', 'Z']:
            continue
        array_ref = accessor.get('source', '').removeprefix('#')
        float_array = source.find(f"./c:float_array[@id='{array_ref}']", namespace)
        if float_array is None or not float_array.text:
            continue
        values = [float(value) for value in float_array.text.split()]
        stride = int(accessor.get('stride', '3'))
        offset = int(accessor.get('offset', '0'))
        count = int(accessor.get('count', '0'))
        sources[source_id] = [
            tuple(values[offset + index * stride:offset + index * stride + 3])
            for index in range(count)
        ]
    return sources


def _vertices_sources(
    root: ET.Element,
    namespace: dict[str, str],
) -> dict[str, str]:
    vertices_sources: dict[str, str] = {}
    for vertices in root.findall('.//c:library_geometries/c:geometry/c:mesh/c:vertices', namespace):
        position = vertices.find("./c:input[@semantic='POSITION']", namespace)
        if vertices.get('id') and position is not None:
            vertices_sources[vertices.get('id')] = position.get('source', '').removeprefix('#')
    return vertices_sources


def _triangulate(indices: list[int]) -> Iterable[tuple[int, int, int]]:
    # 官方 Rhino 文件只包含三角形和四边形；扇形拆分可保持原始顶点顺序。
    for index in range(1, len(indices) - 1):
        yield indices[0], indices[index], indices[index + 1]


def _mesh_triangles(path: Path) -> tuple[list[tuple[tuple[float, float, float], ...]], float]:
    root = ET.parse(path).getroot()
    namespace = _namespace(root)
    scale = _unit_scale(root, namespace)
    sources = _position_sources(root, namespace)
    vertices_sources = _vertices_sources(root, namespace)
    triangles: list[tuple[tuple[float, float, float], ...]] = []

    for mesh in root.findall('.//c:library_geometries/c:geometry/c:mesh', namespace):
        for polygons in mesh.findall('./c:polygons', namespace):
            inputs = polygons.findall('./c:input', namespace)
            if not inputs:
                continue
            index_stride = max(int(item.get('offset', '0')) for item in inputs) + 1
            vertex_input = next(
                (item for item in inputs if item.get('semantic') in {'VERTEX', 'POSITION'}),
                None,
            )
            if vertex_input is None:
                continue
            vertex_offset = int(vertex_input.get('offset', '0'))
            source_id = vertex_input.get('source', '').removeprefix('#')
            if vertex_input.get('semantic') == 'VERTEX':
                source_id = vertices_sources[source_id]
            positions = sources[source_id]

            for polygon in polygons.findall('./c:p', namespace):
                if not polygon.text:
                    continue
                raw_indices = [int(value) for value in polygon.text.split()]
                vertex_indices = raw_indices[vertex_offset::index_stride]
                for triangle_indices in _triangulate(vertex_indices):
                    triangle = tuple(
                        tuple(component * scale for component in positions[index])
                        for index in triangle_indices
                    )
                    triangles.append(triangle)

    if not triangles:
        raise ValueError(f'未从 {path} 中解析出三角形。')
    return triangles, scale


def _normal(triangle: tuple[tuple[float, float, float], ...]) -> tuple[float, float, float]:
    a, b, c = triangle
    ab = tuple(b[index] - a[index] for index in range(3))
    ac = tuple(c[index] - a[index] for index in range(3))
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    length = math.sqrt(sum(component * component for component in cross))
    if length == 0.0:
        return 0.0, 0.0, 0.0
    return tuple(component / length for component in cross)


def _write_binary_stl(
    path: Path,
    triangles: list[tuple[tuple[float, float, float], ...]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b'Platform G2 Pro600 Gazebo mesh'.ljust(80, b' ')
    with path.open('wb') as stream:
        stream.write(header)
        stream.write(struct.pack('<I', len(triangles)))
        for triangle in triangles:
            values = (*_normal(triangle), *triangle[0], *triangle[1], *triangle[2])
            stream.write(struct.pack('<12fH', *values, 0))


def convert_directory(input_dir: Path, output_dir: Path) -> dict[str, object]:
    converted = []
    for mesh_name in MESH_NAMES:
        source = input_dir / f'{mesh_name}.dae'
        if not source.exists():
            raise FileNotFoundError(f'缺少官方网格: {source}')
        triangles, scale = _mesh_triangles(source)
        target = output_dir / f'{mesh_name}.stl'
        _write_binary_stl(target, triangles)
        converted.append({
            'source': str(source),
            'target': str(target),
            'triangle_count': len(triangles),
            'unit_scale': scale,
            'size_bytes': target.stat().st_size,
        })
        print(f'{source.name} -> {target.name}: {len(triangles)} triangles')

    manifest = {
        'format': 'binary_stl',
        'reason': 'Triangulate Rhino COLLADA polygons for Gazebo Ogre2 compatibility.',
        'converted': converted,
    }
    manifest_path = output_dir / 'conversion_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def main() -> int:
    package_root = Path(__file__).resolve().parents[1]
    default_input = (
        package_root
        / 'vendor_ros1/mycobot_description/urdf/mycobot_pro_600'
    )
    default_output = package_root / 'meshes/gazebo'

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=default_input)
    parser.add_argument('--output-dir', type=Path, default=default_output)
    args = parser.parse_args()

    convert_directory(args.input_dir.expanduser().resolve(), args.output_dir.expanduser().resolve())
    print(f'Gazebo 网格已生成: {args.output_dir.expanduser().resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
