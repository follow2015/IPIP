/**
 * DataTable 通用表格组件
 *
 * 【展示组件】纯 Props 驱动，不内部获取数据，不直接订阅 Store。
 *
 * 功能：
 * 1. 统一搜索框：输入时实时同步显示文字，回车/点搜索按钮触发搜索
 * 2. 内置防抖搜索：输入停顿 300ms 后自动触发模糊搜索
 * 3. 可选 Card 包裹：showCard=false 避免嵌套双层边框
 */
import React from 'react';
import { Table, Card, Space, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { TableProps, TablePaginationConfig } from 'antd';
import type { UseTableReturn } from '@/hooks/useTable';
import SearchInput from '@/components/SearchInput';

export type DataTableColumn<T> = NonNullable<TableProps<T>['columns']>[number];

export interface FetchParams {
  page: number;
  per_page: number;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  filters?: Record<string, string | string[]>;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  dataSource: T[];
  loading?: boolean;
  rowKey: string | ((record: T) => string);
  pagination?: false | TablePaginationConfig;
  rowSelection?: TableProps<T>['rowSelection'];
  onRow?: TableProps<T>['onRow'];
  toolbar?: React.ReactNode;
  emptyText?: string;
  searchable?: boolean;
  searchPlaceholder?: string;
  searchValue?: string;
  onSearch?: (value: string) => void;
  searchDebounce?: number;
  onRefresh?: () => void;
  total?: number;
  page?: number;
  perPage?: number;
  onPageChange?: (page: number, perPage: number) => void;
  showCard?: boolean;
  tableProps?: UseTableReturn;
}

function DataTable<T extends object>({
  columns,
  dataSource,
  loading = false,
  rowKey,
  pagination,
  rowSelection,
  onRow,
  toolbar,
  emptyText = '暂无数据',
  searchable = true,
  searchPlaceholder = '搜索...',
  searchValue,
  onSearch,
  searchDebounce = 300,
  onRefresh,
  total,
  page,
  perPage,
  onPageChange,
  showCard = true,
  tableProps
}: DataTableProps<T>) {
  const resolvedPage = page ?? tableProps?.page;
  const resolvedPerPage = perPage ?? tableProps?.perPage;
  const resolvedTotal = total ?? tableProps?.total;
  const resolvedSearchValue = searchValue ?? tableProps?.search;
  const resolvedOnSearch = onSearch ?? tableProps?.setSearch;
  const resolvedOnPageChange =
    onPageChange ??
    ((p: number, ps: number) => {
      tableProps?.setPage(p);
      if (ps !== tableProps?.perPage) tableProps?.setPerPage(ps);
    });
  const paginationConfig: false | TablePaginationConfig =
    pagination === false
      ? false
      : {
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (t) => `共 ${t} 条`,
          ...pagination,
          current: resolvedPage,
          pageSize: resolvedPerPage,
          total: resolvedTotal ?? 0,
          onChange: (p, ps) => resolvedOnPageChange?.(p, ps)
        };

  const hasToolbar = searchable || toolbar || onRefresh;

  const content = (
    <>
      {hasToolbar && (
        <div
          style={{
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8
          }}
        >
          <Space wrap>
            {searchable && (
              <SearchInput
                value={resolvedSearchValue}
                onSearch={resolvedOnSearch ?? (() => {})}
                placeholder={searchPlaceholder}
                debounce={searchDebounce}
              />
            )}
            {onRefresh && (
              <Button
                icon={<ReloadOutlined />}
                onClick={onRefresh}
                title="刷新"
                aria-label="刷新"
              />
            )}
          </Space>
          {toolbar && <Space>{toolbar}</Space>}
        </div>
      )}
      <Table<T>
        columns={columns}
        dataSource={dataSource}
        loading={loading}
        rowKey={rowKey}
        pagination={paginationConfig}
        rowSelection={rowSelection}
        onRow={onRow}
        locale={{ emptyText }}
        scroll={{ x: 'max-content' }}
      />
    </>
  );

  return showCard ? <Card>{content}</Card> : <>{content}</>;
}

export default DataTable;
