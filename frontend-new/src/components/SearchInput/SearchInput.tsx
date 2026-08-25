/**
 * 通用搜索输入组件
 *
 * 【展示组件】纯 Props 驱动，不内部获取数据，不直接订阅 Store。
 *
 * - 输入时实时显示文字，防抖后自动触发搜索
 * - 回车/点击搜索按钮立即触发
 * - 清空时立即触发空搜索
 * - 防抖期间外部 value 回写不会打断用户正在输入的内容
 */
import React, { useState, useEffect, useRef } from 'react';
import { Input } from 'antd';

export interface SearchInputProps {
  
  value?: string;
  
  onSearch: (value: string) => void;
  
  placeholder?: string;
  
  debounce?: number;
  
  style?: React.CSSProperties;
  
  size?: 'small' | 'middle' | 'large';
}

function SearchInput({
  value,
  onSearch,
  placeholder = '搜索...',
  debounce = 300,
  style = { width: 300 },
  size,
}: SearchInputProps) {
  const [localValue, setLocalValue] = useState(value ?? '');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const isUserEditingRef = useRef(false);

  
  useEffect(() => {
    if (value !== undefined && !isUserEditingRef.current) {
      setLocalValue(value);
    }
  }, [value]);

  
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleChange = (newValue: string) => {
    isUserEditingRef.current = true;
    setLocalValue(newValue);
    if (debounce > 0 && onSearch) {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onSearch(newValue);
        isUserEditingRef.current = false;
      }, debounce);
    }
  };

  const handleSearch = (searchValue: string) => {
    clearTimeout(debounceRef.current);
    isUserEditingRef.current = false;
    onSearch(searchValue);
  };

  const handleClear = () => {
    setLocalValue('');
    clearTimeout(debounceRef.current);
    isUserEditingRef.current = false;
    onSearch('');
  };

  return (
    <Input.Search
      placeholder={placeholder}
      value={localValue}
      onChange={(e) => handleChange(e.target.value)}
      onSearch={handleSearch}
      onClear={handleClear}
      allowClear
      style={style}
      size={size}
    />
  );
}

export default SearchInput;
