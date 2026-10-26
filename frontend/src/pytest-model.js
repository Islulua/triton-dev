// Group by source function/class identity, never by a user-supplied case_id.
export function groupCases(items) {
  const groups = new Map();
  for (const item of items) {
    const offset = item.nodeid.lastIndexOf('::') + 2;
    const parameter = item.nodeid.indexOf('[', offset);
    const logical = item.logical_nodeid || (parameter < 0 ? item.nodeid : item.nodeid.slice(0, parameter));
    if (!groups.has(logical)) groups.set(logical, { id: logical, cases: [], markers: new Set() });
    const group = groups.get(logical);
    group.cases.push(item);
    (item.markers || []).forEach(marker => group.markers.add(marker));
  }
  return [...groups.values()].map(group => ({ ...group, markers: [...group.markers] }));
}
export function selectConfigurations(previous, nodeids, checked) {
  const visible = new Set(nodeids);
  return checked ? [...new Set([...previous, ...nodeids])] : previous.filter(id => !visible.has(id));
}
