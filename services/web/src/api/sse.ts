export interface SseEvent<T = Record<string, unknown>> {
  name: string;
  data: T;
}

export function parseSseBlock<T = Record<string, unknown>>(block: string): SseEvent<T> | null {
  let name = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return null;
  return { name, data: JSON.parse(dataLines.join("\n")) as T };
}
