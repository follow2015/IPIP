import type { RoomOverviewGroup, RoomOverviewItem } from '@/types/models';

export interface OverviewFilter {
  name?: string;
  building?: string;
  floor?: string;
  keyword?: string;
}

export function isFilterEmpty(filter: OverviewFilter): boolean {
  return !filter.name && !filter.building && !filter.floor && !filter.keyword?.trim();
}

function matchRoom(room: RoomOverviewItem, filter: OverviewFilter): boolean {
  if (filter.building && room.building !== filter.building) return false;
  if (filter.floor && room.floor !== filter.floor) return false;

  const keyword = filter.keyword?.trim().toLowerCase();
  if (keyword && !(room.name ?? '').toLowerCase().includes(keyword)) return false;

  return true;
}

export function filterOverviewGroups(
  groups: RoomOverviewGroup[],
  filter: OverviewFilter
): RoomOverviewGroup[] {
  if (isFilterEmpty(filter)) return groups;

  const result: RoomOverviewGroup[] = [];

  for (const group of groups) {
    if (filter.name && group.name !== filter.name) continue;

    const rooms = group.rooms.filter((room) => matchRoom(room, filter));
    if (rooms.length === 0) continue;

    result.push({
      ...group,
      room_count: rooms.length,
      cabinet_count: rooms.reduce((sum, room) => sum + (room.cabinet_count ?? 0), 0),
      rooms
    });
  }

  return result;
}

export function countRooms(groups: RoomOverviewGroup[]): number {
  return groups.reduce((sum, group) => sum + group.rooms.length, 0);
}

export function collectFloors(groups: RoomOverviewGroup[]): string[] {
  const set = new Set<string>();
  for (const group of groups) {
    for (const room of group.rooms) {
      if (room.floor) set.add(room.floor);
    }
  }
  return [...set].sort();
}
