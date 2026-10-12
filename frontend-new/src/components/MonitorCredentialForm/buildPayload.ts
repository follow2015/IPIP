
export function buildCredentialPayload(
  protocol: string,
  values: Record<string, unknown>
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};

  if (protocol === 'snmp') {
    const ver = (values.snmp_version as string) || 'v2c';
    payload.snmp_version = ver;
    if (ver === 'v2c') {
      payload.community = values.community;
    } else {
      payload.username = values.username;
      payload.auth_key = values.auth_key;
      payload.priv_key = values.priv_key;
      payload.auth_protocol = values.auth_protocol || 'sha';
      payload.priv_protocol = values.priv_protocol || 'aes';
    }
  } else if (protocol === 'zabbix') {
    payload.api_url = values.api_url;
    payload.api_token = values.api_token;
    if (values.verify_ssl != null) payload.verify_ssl = values.verify_ssl;
    if (values.match_by) payload.match_by = values.match_by;
  } else {
    payload.username = values.username;
    payload.password = values.password;
    if (values.verify_ssl != null) payload.verify_ssl = values.verify_ssl;
  }

  return payload;
}
