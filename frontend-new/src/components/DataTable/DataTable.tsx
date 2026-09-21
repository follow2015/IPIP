import React from 'react';
import { Table, Card, Space, Button, List, Pagination, Checkbox } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { TableProps, TablePaginationConfig, CheckboxProps } from 'antd';
import type { UseTableReturn } from '@/hooks/useTable';
import SearchInput from '@/components/SearchInput';
import { useResponsive } from '@/hooks/useResponsive';
import { formatLimitHint, isBeyondOffsetLimit } from './serverPagination';

type CheckboxChangeEvent = Parameters<NonNullable<CheckboxProps['onChange']>>[0];

export type DataTableColumn<T> = NonNullable<TableProps<T>['columns']>[number];

const DEFAULT_SCROLL = { x: 'max-content' } satisfies NonNullable<TableProps<never>['scroll']>;

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
  emptyText?: React.ReactNode;
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
  filters?: React.ReactNode;
  actions?: React.ReactNode;
  mobileCardMode?: boolean;
  cardRender?: (record: T) => React.ReactNode;
  size?: TableProps<T>['size'];
  rowClassName?: TableProps<T>['rowClassName'];
  scroll?: TableProps<T>['scroll'];
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
  tableProps,
  filters,
  actions,
  mobileCardMode = false,
  cardRender,
  size,
  rowClassName,
  scroll = DEFAULT_SCROLL
}: DataTableProps<T>) {
  const { isMobile } = useResponsive();
  const hasToolbar = searchable || toolbar || onRefresh || filters || actions;
  const showAsCard = mobileCardMode && isMobile && !!cardRender;
  const resolvedPage = page ?? tableProps?.page;
  const resolvedPerPage = perPage ?? tableProps?.perPage;
  const resolvedTotal = total ?? tableProps?.total;
  const resolvedSearchValue = searchValue ?? tableProps?.search;
  const resolvedOnSearch = onSearch ?? tableProps?.setSearch;
  const resolvedOnPageChange =
    onPageChange ??
    (tableProps
      ? (p: number, ps: number) => {
          tableProps.setPage(p);
          if (ps !== tableProps.perPage) tableProps.setPerPage(ps);
        }
      : pagination !== false
        ? pagination?.onChange
        : undefined);
  const beyondOffsetLimit = isBeyondOffsetLimit(resolvedTotal);
  const basePagination: TablePaginationConfig = showAsCard
    ? { simple: true, showSizeChanger: false, showQuickJumper: false }
    : beyondOffsetLimit
      ? { showSizeChanger: true, showQuickJumper: false, showTotal: formatLimitHint }
      : { showSizeChanger: true, showQuickJumper: true, showTotal: (t) => `共 ${t} 条` };
  const paginationConfig: false | TablePaginationConfig =
    pagination === false
      ? false
      : {
          ...basePagination,
          ...pagination,
          ...(resolvedPage !== undefined ? { current: resolvedPage } : {}),
          ...(resolvedPerPage !== undefined ? { pageSize: resolvedPerPage } : {}),
          ...(resolvedTotal !== undefined ? { total: resolvedTotal } : {}),
          ...(resolvedOnPageChange ? { onChange: resolvedOnPageChange } : {})
        };

  const rowKeyFn: (r: T) => string =
    typeof rowKey === 'function'
      ? rowKey
      : (r: T) => String((r as Record<string, unknown>)[rowKey]);
  const selectedKeys = (rowSelection?.selectedRowKeys ?? []) as React.Key[];
  const rowsByKeys = (keys: React.Key[]) => {
    const set = new Set(keys.map(String));
    return dataSource.filter((r) => set.has(rowKeyFn(r)));
  };
  const handleCardCheck = (record: T) => (e: CheckboxChangeEvent) => {
    const key = rowKeyFn(record);
    const next = e.target.checked ? [...selectedKeys, key] : selectedKeys.filter((k) => k !== key);
    rowSelection?.onChange?.(next, rowsByKeys(next), { type: 'single' });
  };

  const pageKeys = dataSource.map((r) => rowKeyFn(r));
  const selectedKeySet = new Set(selectedKeys.map(String));
  const pageSelectedCount = pageKeys.filter((k) => selectedKeySet.has(k)).length;
  const allPageSelected = pageKeys.length > 0 && pageSelectedCount === pageKeys.length;
  const somePageSelected = pageSelectedCount > 0 && !allPageSelected;
  const handleCardCheckAll = (e: CheckboxChangeEvent) => {
    if (e.target.checked) {
      const next = Array.from(new Set([...selectedKeys.map(String), ...pageKeys]));
      rowSelection?.onChange?.(next, rowsByKeys(next), { type: 'all' });
      return;
    }
    const pageSet = new Set(pageKeys);
    const next = selectedKeys.filter((k) => !pageSet.has(String(k)));
    rowSelection?.onChange?.(next, rowsByKeys(next), { type: 'all' });
  };

  const content = (
    <>
      {hasToolbar && (
        <div
          style={{
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
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
            {filters}
          </Space>
          {(actions || toolbar) && (
            <Space wrap>
              {actions}
              {toolbar}
            </Space>
          )}
        </div>
      )}
      {showAsCard ? (
        <>
          {rowSelection && dataSource.length > 0 && (
            <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center' }}>
              <Checkbox
                checked={allPageSelected}
                indeterminate={somePageSelected}
                onChange={handleCardCheckAll}
              >
                全选本页（{dataSource.length} 条）
              </Checkbox>
            </div>
          )}
          <List<T>
            dataSource={dataSource}
            rowKey={rowKeyFn}
            loading={loading}
            split={false}
            locale={{ emptyText }}
            renderItem={(record) => (
              <List.Item style={{ padding: '8px 0' }}>
                <Card
                  size="small"
                  style={{ width: '100%' }}
                  title={
                    rowSelection ? (
                      <Checkbox
                        checked={selectedKeySet.has(String(rowKeyFn(record)))}
                        disabled={rowSelection.getCheckboxProps?.(record)?.disabled}
                        onChange={handleCardCheck(record)}
                      />
                    ) : undefined
                  }
                >
                  {cardRender(record)}
                </Card>
              </List.Item>
            )}
          />
          {paginationConfig !== false && (
            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
              <Pagination {...paginationConfig} size={isMobile ? 'small' : undefined} />
            </div>
          )}
        </>
      ) : (
        <Table<T>
          columns={columns}
          dataSource={dataSource}
          loading={loading}
          rowKey={rowKey}
          pagination={paginationConfig}
          rowSelection={rowSelection}
          onRow={onRow}
          locale={{ emptyText }}
          scroll={scroll}
          size={size}
          rowClassName={rowClassName}
        />
      )}
    </>
  );

  return showCard ? <Card>{content}</Card> : <>{content}</>;
}

export default DataTable;
