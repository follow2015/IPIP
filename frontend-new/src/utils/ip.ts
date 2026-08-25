/**
 * IP 地址工具
 * - 校验/格式化/计算
 */
import * as ipaddr from 'ipaddr.js';


export function isValidIP(ip: string): boolean {
  try {
    return ipaddr.IPv4.isValidFourPartDecimal(ip) || ipaddr.IPv6.isValid(ip);
  } catch {
    return false;
  }
}


export function isValidIPv4(ip: string): boolean {
  try {
    return ipaddr.IPv4.isValidFourPartDecimal(ip);
  } catch {
    return false;
  }
}


export function isValidSubnetMask(mask: string): boolean {
  if (!isValidIPv4(mask)) return false;
  const parsed = ipaddr.IPv4.parse(mask);
  const binary = parsed.octets.map((o) => o.toString(2).padStart(8, '0')).join('');
  return /^1+0*$/.test(binary);
}


export function isValidNetwork(address: string, mask: string): boolean {
  if (!isValidIPv4(address) || !isValidSubnetMask(mask)) return false;
  return true;
}


export function formatIP(ip: string): string {
  return ip.trim();
}


export function calculateAvailableIPs(subnetMask: string): number {
  if (!isValidSubnetMask(subnetMask)) return 0;
  const parsed = ipaddr.IPv4.parse(subnetMask);
  const binary = parsed.octets.map((o) => o.toString(2).padStart(8, '0')).join('');
  const zeroBits = binary.split('').filter((b) => b === '0').length;
  return Math.pow(2, zeroBits) - 2; 
}


export function getCIDRPrefix(subnetMask: string): number {
  if (!isValidSubnetMask(subnetMask)) return 0;
  const parsed = ipaddr.IPv4.parse(subnetMask);
  const binary = parsed.octets.map((o) => o.toString(2).padStart(8, '0')).join('');
  return binary.split('').filter((b) => b === '1').length;
}


export function isPrivateIPv4(ip: string): boolean {
  try {
    if (!ipaddr.IPv4.isValidFourPartDecimal(ip)) return false;
    const octets = ipaddr.IPv4.parse(ip).octets;
    
    if (octets[0] === 10) return true;
    
    if (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) return true;
    
    if (octets[0] === 192 && octets[1] === 168) return true;
    return false;
  } catch {
    return false;
  }
}


export function isPrivateNetwork(cidr: string): boolean {
  try {
    const parts = cidr.split('/');
    if (parts.length !== 2) return false;
    return isPrivateIPv4(parts[0]);
  } catch {
    return false;
  }
}


export interface ParsedIPEntry {
  
  raw: string;
  
  display: string;
  
  isNetwork: boolean;
  
  isRange: boolean;
  
  valid: boolean;
}


export function subnetMaskToCIDR(mask: string): number | null {
  if (!isValidSubnetMask(mask)) return null;
  return getCIDRPrefix(mask);
}


export function parseIPSegment(segment: string): ParsedIPEntry {
  const s = segment.trim();
  if (!s) return { raw: s, display: s, isNetwork: false, isRange: false, valid: false };

  
  const cidrMatch = s.match(/^(\d+\.\d+\.\d+\.\d+)\/(\d+)$/);
  if (cidrMatch) {
    const [, network, prefix] = cidrMatch;
    if (isValidIPv4(network) && +prefix >= 0 && +prefix <= 32) {
      return { raw: s, display: `${network}/${prefix}`, isNetwork: true, isRange: false, valid: true };
    }
    return { raw: s, display: s, isNetwork: false, isRange: false, valid: false };
  }

  
  const maskMatch = s.match(/^(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)$/);
  if (maskMatch) {
    const [, network, mask] = maskMatch;
    const cidr = subnetMaskToCIDR(mask);
    if (cidr !== null && isValidIPv4(network)) {
      return { raw: s, display: `${network}/${cidr}`, isNetwork: true, isRange: false, valid: true };
    }
    return { raw: s, display: s, isNetwork: false, isRange: false, valid: false };
  }

  
  const rangeMatch = s.match(/^(\d+\.\d+\.\d+\.\d+)-(.+)$/);
  if (rangeMatch) {
    const [, startIP, endPart] = rangeMatch;
    if (!isValidIPv4(startIP)) {
      return { raw: s, display: s, isNetwork: false, isRange: false, valid: false };
    }
    const startOctets = startIP.split('.').map(Number);

    if (isValidIPv4(endPart)) {
      
      const endOctets = endPart.split('.').map(Number);
      
      if (startOctets[0] === endOctets[0] && startOctets[1] === endOctets[1] && startOctets[2] === endOctets[2] && endOctets[3] >= startOctets[3]) {
        const display = startOctets[3] === endOctets[3]
          ? startIP
          : `${startIP}-${endOctets[3]}`;
        return { raw: s, display, isNetwork: false, isRange: startOctets[3] !== endOctets[3], valid: true };
      }
      return { raw: s, display: s, isNetwork: false, isRange: false, valid: false };
    }

    
    const endNum = Number(endPart);
    if (Number.isInteger(endNum) && endNum >= 0 && endNum <= 255 && endNum >= startOctets[3]) {
      const display = startOctets[3] === endNum
        ? startIP
        : `${startIP}-${endNum}`;
      return { raw: s, display, isNetwork: false, isRange: startOctets[3] !== endNum, valid: true };
    }
    return { raw: s, display: s, isNetwork: false, isRange: false, valid: false };
  }

  
  if (isValidIPv4(s) || isValidIP(s)) {
    return { raw: s, display: s, isNetwork: false, isRange: false, valid: true };
  }

  return { raw: s, display: s, isNetwork: false, isRange: false, valid: false };
}


export function parseIPAddressString(ipString: string | null | undefined): ParsedIPEntry[] {
  if (!ipString) return [];
  return ipString.split(',').map(seg => parseIPSegment(seg)).filter(e => e.raw);
}


export function serializeIPEntries(entries: ParsedIPEntry[]): string {
  return entries.map(e => e.raw).join(',');
}


export function removeIPAtIndex(ipString: string | null | undefined, index: number): string {
  const entries = parseIPAddressString(ipString);
  const filtered = entries.filter((_, i) => i !== index);
  return serializeIPEntries(filtered);
}
