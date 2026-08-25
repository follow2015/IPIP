/**
 * FilterBar 通用筛选栏组件
 *
 * 【展示组件】纯 Props 驱动，声明式配置筛选控件。
 * 对接 useTable 的 filters/updateFilter，自动处理分页重置和联动重置。
 *
 * 用法：
 * <FilterBar
 *   filters={[
 *     { key: 'room_id', label: '机房', type: 'select', options: roomOptions },
 *     { key: 'status', label: '状态', type: 'select', options: statusOptions },
 *   ]}
 *   table={table}
 * />
 */
import React from 'react';
import { Select, Space, DatePicker } from 'antd';
import type { UseTableReturn } from '@/hooks/useTable';

const { RangePicker } = DatePicker;


export interface FilterItem {
  
  key: string;
  
  label: string;
  
  type: 'select' | 'rangePicker';
  
  options?: { label: string; value: string | number | boolean }[];
  
  width?: number;
  
  visible?: (filters: Record<string, string | string[]>) => boolean;
  
  showSearch?: boolean;
  
  onSearch?: (value: string) => void;
  
  placeholders?: [string, string];
}

export interface FilterBarProps {
  
  filters: FilterItem[];
  
  table: UseTableReturn;
  
  extra?: React.ReactNode;
  
  prefix?: React.ReactNode;
}

function FilterBar({ filters, table, extra, prefix }: FilterBarProps) {
  const { filters: filterValues, updateFilter } = table;

  return (
    <Space wrap>
      {prefix}
      {filters.map((item) => {
        
        if (item.visible && !item.visible(filterValues)) return null;

        const currentValue = filterValues[item.key];

        if (item.type === 'select') {
          
          const selectValue = currentValue !== undefined
            ? item.options?.find(o => String(o.value) === currentValue)?.value ?? currentValue
            : undefined;

          return (
            <Select
              key={item.key}
              placeholder={item.label}
              options={item.options}
              allowClear
              showSearch={item.showSearch}
              filterOption={item.showSearch
                ? (input, option) =>
                    (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                : undefined
              }
              onSearch={item.onSearch}
              style={{ width: item.width ?? 150 }}
              value={selectValue}
              onChange={(v) => { if (typeof v !== 'object') updateFilter(item.key, v); }}
            />
          );
        }

        if (item.type === 'rangePicker') {
          return (
            <RangePicker
              key={item.key}
              placeholder={item.placeholders ?? ['开始日期', '结束日期']}
              onChange={(dates) => {
                if (dates && dates[0] && dates[1]) {
                  updateFilter(item.key, `${dates[0].format('YYYY-MM-DD')}~${dates[1].format('YYYY-MM-DD')}`);
                } else {
                  updateFilter(item.key, undefined);
                }
              }}
            />
          );
        }

        return null;
      })}
      {extra}
    </Space>
  );
}

export default FilterBar;
