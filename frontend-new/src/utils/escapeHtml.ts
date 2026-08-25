/**
 * escapeHtml — 转义 HTML 特殊字符，防止存储型 XSS。
 *
 * 用于把不可信文本安全插入 innerHTML / HTML 字符串。
 * 本系统是网络设备管理：设备名 / IP / 机房名常经 SNMP 自动扫描入库，
 * 属不可信边界，凡拼进 HTML 的字段都必须先转义。
 */
export function escapeHtml(input?: string | null): string {
  if (input == null) return '';
  return String(input).replace(/[&<>"']/g, (ch) => {
    switch (ch) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      case "'":
        return '&#39;';
      default:
        return ch;
    }
  });
}
