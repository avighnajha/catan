"""Portable ANSI/plain-text rendering of the actual board topology."""
import math

RESOURCE_COLORS = {'WOOD': 32, 'BRICK': 31, 'SHEEP': 92, 'WHEAT': 93, 'ORE': 90, 'DESERT': 33}
PLAYER_COLORS = {'P1': 91, 'P2': 94, 'P3': 97, 'P4': 95}


def board_text(sim, color=False):
    cells = {}
    def put(x, y, text, code=None):
        for i, char in enumerate(text):
            cells[x+i, y] = f'\033[{code}m{char}\033[0m' if color and code else char
    points = {v: (round(d.coordinate.x / (math.sqrt(3)/2)*6)+32,
                  round(d.coordinate.y*4)+18) for v,d in sim.board_geometry.vertices.items()}
    for eid, edge in sim.board_geometry.edges.items():
        a,b = [points[v] for v in sorted(edge.vertex_ids)]
        length = max(abs(a[0]-b[0]), abs(a[1]-b[1]))
        owner = sim._road_owner(eid)
        char = '|' if a[0]==b[0] else '/' if (b[0]-a[0])*(b[1]-a[1])<0 else '\\'
        for i in range(1,length):
            put(round(a[0]+(b[0]-a[0])*i/length), round(a[1]+(b[1]-a[1])*i/length),
                char, PLAYER_COLORS.get(owner.value) if owner else None)
    for tid,tile in sim.board.tiles.items():
        endpoints = [points[v] for v in sim.board_geometry.tiles[tid].vertex_ids]
        x = round(sum(p[0] for p in endpoints)/6)
        y = round(sum(p[1] for p in endpoints)/6)
        resource = tile.resource_type.value if tile.resource_type else 'DESERT'
        put(x-2,y-1,str(tid),RESOURCE_COLORS[resource])
        put(x-2,y,resource[:3],RESOURCE_COLORS[resource])
        put(x-2,y+1,f'{tile.number_token or "-"}{" R" if tile.has_robber else ""}',RESOURCE_COLORS[resource])
    for vid,(x,y) in points.items():
        building = sim._building(vid)
        put(x,y,('C' if building.type.value=='CITY' else 'S') if building.owner else '+',
            PLAYER_COLORS.get(building.owner.value) if building.owner else None)
    lines = [''.join(cells.get((x,y),' ') for x in range(65)).rstrip() for y in range(37)]
    lines.append('S settlement / C city / coloured edges roads / R robber')
    for pid in sim.order:
        buildings = [f'{v}:{sim._building(v).type.value}' for v in points if sim._building(v).owner==pid]
        roads = [e for e in sim.board_geometry.edges if sim._road_owner(e)==pid]
        label = f'\033[{PLAYER_COLORS[pid.value]}m{pid.value}\033[0m' if color else pid.value
        lines.append(f'{label}: buildings {", ".join(buildings) or "none"}; roads {", ".join(roads) or "none"}')
    lines.append('Ports: '+ '; '.join(f'{p.port_type.value} at {",".join(sorted(p.vertex_ids))}' for p in sim.board_geometry.ports.values()))
    return '\n'.join(lines)
