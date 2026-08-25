import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { physicalToInternal, internalToPhysical, displayLabel, checkConflict } from './geometry';
import { computeLayout } from './layout';
import type { LayoutMetrics } from './layout';
import type { OccupiedPosition, UPositionSelectorProps } from './types';

export interface RackStats {
  usedU: number;
  usedP: number;
  uPct: number;
  pPct: number;
}

export type DropMsg = { text: string; type: 'ok' | 'err' | '' };

export interface UseRackLayoutResult {
  devices: OccupiedPosition[];
  selectedId: number | null;
  dragId: number | null;
  highlightUs: number[];
  dropMsg: DropMsg;
  collapsed: Record<number, boolean>;
  containerWidth: number;
  containerRef: React.RefObject<HTMLDivElement | null>;
  bodyRef: React.RefObject<HTMLDivElement | null>;
  layout: LayoutMetrics;
  stats: RackStats;
  occupiedSet: Set<number>;
  selectedDevice: OccupiedPosition | null;
  totalH: number;
  handleSelect: (id: number) => void;
  handleDragStart: (e: React.DragEvent, id: number, offsetInDevice: number) => void;
  handleDragEnd: () => void;
  handleSlotDragOver: (e: React.DragEvent) => void;
  handleSlotDrop: (e: React.DragEvent) => void;
  clearHighlight: () => void;
  toggleCollapse: (deviceId: number) => void;
}


export function useRackLayout(props: UPositionSelectorProps): UseRackLayoutResult {
  const { totalU = 42, ratedPower = 8000, occupiedPositions, onPositionChange, onSelect } = props;

  
  const [devices, setDevices] = useState<OccupiedPosition[]>(() =>
    occupiedPositions.map((p) => ({ ...p, uPosition: physicalToInternal(p.uPosition, totalU) }))
  );
  const committedRef = useRef<Map<number, number>>(new Map()); 

  
  const toInternal = useCallback(
    (physicalU: number): number => {
      return physicalToInternal(physicalU, totalU);
    },
    [totalU]
  );

  
  const toPhysical = useCallback(
    (internalU: number): number => {
      return internalToPhysical(internalU, totalU);
    },
    [totalU]
  );

  
  useEffect(() => {
    setDevices(() => {
      return occupiedPositions.map((incoming) => {
        const committedPhysical = committedRef.current.get(incoming.deviceId);
        if (committedPhysical !== undefined) {
          
          if (incoming.uPosition === committedPhysical) {
            committedRef.current.delete(incoming.deviceId);
            return { ...incoming, uPosition: toInternal(incoming.uPosition) };
          }
          
          return { ...incoming, uPosition: toInternal(committedPhysical) };
        }
        return { ...incoming, uPosition: toInternal(incoming.uPosition) };
      });
    });
  }, [occupiedPositions, toInternal]);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);
  const [dragOffsetInDevice, setDragOffsetInDevice] = useState(0);
  const [dropMsg, setDropMsg] = useState<DropMsg>({ text: '', type: '' });
  const [highlightUs, setHighlightUs] = useState<number[]>([]);
  
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});

  const containerRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const msgTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  
  const [containerWidth, setContainerWidth] = useState(500);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const layout = useMemo(() => computeLayout(containerWidth), [containerWidth]);

  
  const usedU = devices.reduce((s, d) => s + d.uSize, 0);
  const usedP = devices.reduce((s, d) => s + (d.power ?? 0), 0);
  const uPct = Math.round((usedU / totalU) * 100);
  const pPct = Math.round((usedP / ratedPower) * 100);

  const handleSelect = (id: number) => {
    const d = devices.find((x) => x.deviceId === id) ?? null;
    setSelectedId(id);
    onSelect?.(d);
  };

  const handleDragStart = useCallback((e: React.DragEvent, id: number, offsetInDevice: number) => {
    setDragId(id);
    setDragOffsetInDevice(offsetInDevice);
    e.dataTransfer.effectAllowed = 'move';
  }, []);

  const handleDragEnd = useCallback(() => {
    setDragId(null);
    setHighlightUs([]);
  }, []);

  
  const getDropTarget = useCallback(
    (e: React.DragEvent, device: OccupiedPosition): number => {
      if (!bodyRef.current) return device.uPosition;
      const rect = bodyRef.current.getBoundingClientRect();
      const relY = e.clientY - rect.top;
      const mouseU = Math.floor(relY / layout.unit) + 1; 
      const newStart = mouseU - dragOffsetInDevice;
      return Math.max(1, Math.min(totalU - device.uSize + 1, newStart));
    },
    [dragOffsetInDevice, totalU, layout.unit]
  );

  const handleSlotDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      if (dragId === null) return;
      const device = devices.find((d) => d.deviceId === dragId);
      if (!device) return;
      const newStart = getDropTarget(e, device);
      const hl: number[] = [];
      for (let u = newStart; u < newStart + device.uSize && u <= totalU; u++) hl.push(u);
      setHighlightUs(hl);
      const conflict = checkConflict(devices, dragId, newStart, device.uSize);

      
      const dispStart = displayLabel(newStart, totalU);
      const dispEnd = displayLabel(newStart + device.uSize - 1, totalU);
      const uRangeStr = `U${dispEnd}–U${dispStart}`;

      setDropMsg({
        text: conflict ? `${uRangeStr} 位置冲突` : `放置到 ${uRangeStr}`,
        type: conflict ? 'err' : 'ok'
      });
    },
    [dragId, devices, getDropTarget, totalU]
  );

  const handleSlotDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (dragId === null) return;
      const device = devices.find((d) => d.deviceId === dragId);
      if (!device) return;
      const newStart = getDropTarget(e, device);

      if (checkConflict(devices, dragId, newStart, device.uSize)) {
        setDropMsg({ text: '位置冲突，移动取消', type: 'err' });
        clearTimeout(msgTimer.current);
        msgTimer.current = setTimeout(() => setDropMsg({ text: '', type: '' }), 2500);
        return;
      }

      
      const physicalPos = toPhysical(newStart);
      committedRef.current.set(dragId, physicalPos);
      const next = devices.map((d) => (d.deviceId === dragId ? { ...d, uPosition: newStart } : d));
      setDevices(next);
      setHighlightUs([]);
      setDragId(null);

      
      const dispStart = displayLabel(newStart, totalU);
      const dispEnd = displayLabel(newStart + device.uSize - 1, totalU);
      const uRangeStr = `U${dispEnd}–U${dispStart}`;
      setDropMsg({ text: `${device.deviceName} 已移至 ${uRangeStr}`, type: 'ok' });
      clearTimeout(msgTimer.current);
      msgTimer.current = setTimeout(() => setDropMsg({ text: '', type: '' }), 2500);

      
      onPositionChange?.(dragId, physicalPos);
    },
    [dragId, devices, getDropTarget, onPositionChange, totalU, toPhysical]
  );

  const toggleCollapse = useCallback((deviceId: number) => {
    setCollapsed((c) => ({ ...c, [deviceId]: !c[deviceId] }));
  }, []);

  const clearHighlight = useCallback(() => {
    setHighlightUs([]);
  }, []);

  
  const occupiedSet = useMemo(() => {
    const s = new Set<number>();
    devices.forEach((d) => {
      for (let i = 0; i < d.uSize; i++) s.add(d.uPosition + i);
    });
    return s;
  }, [devices]);

  const selectedDevice =
    selectedId != null ? (devices.find((d) => d.deviceId === selectedId) ?? null) : null;
  const totalH = totalU * layout.unit - 2; 

  return {
    devices,
    selectedId,
    dragId,
    highlightUs,
    dropMsg,
    collapsed,
    containerWidth,
    containerRef,
    bodyRef,
    layout,
    stats: { usedU, usedP, uPct, pPct },
    occupiedSet,
    selectedDevice,
    totalH,
    handleSelect,
    handleDragStart,
    handleDragEnd,
    handleSlotDragOver,
    handleSlotDrop,
    clearHighlight,
    toggleCollapse
  };
}
