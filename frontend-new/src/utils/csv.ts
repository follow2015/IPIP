/**
 * CSV 导出/导入工具
 * - exportCSV: 前端生成 CSV 下载
 * - parseCSV: 解析 CSV 文件内容
 * - useExportCSV: React Hook，返回导出函数
 */
import { useCallback } from 'react';

import { message } from 'antd';


interface ExportCSVOptions {
  
  filename?: string;
  
  withBOM?: boolean;
}


export function exportCSV(
  headers: string[],
  rows: (string | number | null | undefined)[][],
  options?: ExportCSVOptions,
): void {
  const { filename = 'export', withBOM = true } = options ?? {};
  const csv = [headers, ...rows]
    .map((row) => row.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(','))
    .join('\n');
  const blob = new Blob([withBOM ? '\uFEFF' + csv : csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}


export function useExportCSV() {
  return useCallback(
    <T extends Record<string, unknown>>(
      data: T[],
      columns: { key: keyof T; title: string }[],
      filename?: string,
    ) => {
      if (!data.length) {
        message.warning('无数据可导出');
        return;
      }
      const headers = columns.map((c) => c.title);
      const rows = data.map((item) => columns.map((c) => String(item[c.key] ?? '')));
      exportCSV(headers, rows, { filename });
    },
    [],
  );
}


export function parseCSV(text: string): string[][] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  return lines.map((line) => {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuotes) {
        if (ch === '"' && line[i + 1] === '"') {
          current += '"';
          i++;
        } else if (ch === '"') {
          inQuotes = false;
        } else {
          current += ch;
        }
      } else {
        if (ch === '"') {
          inQuotes = true;
        } else if (ch === ',') {
          result.push(current);
          current = '';
        } else {
          current += ch;
        }
      }
    }
    result.push(current);
    return result;
  });
}
