/**
 * 导入导出服务
 * - 模板下载 + 文件导入 + 数据导出
 */
import { useMutation } from '@tanstack/react-query';
import { ImportExportType, DeviceType } from '@/types/enums';
import apiClient from './api-client';

export interface DownloadTemplateParams {
  type: ImportExportType;
  deviceTemplateType?: DeviceType;
}

async function downloadTemplate(params: DownloadTemplateParams) {
  const templatePaths: Record<ImportExportType, string> = {
    [ImportExportType.DEVICE]: '/devices/import-template',
    [ImportExportType.CUSTOMER]: '/customers/import-template',
    [ImportExportType.CABINET]: '/cabinets/import-template'
  };
  const path = templatePaths[params.type];
  const queryParams: Record<string, string> = {};
  if (params.type === ImportExportType.DEVICE && params.deviceTemplateType) {
    queryParams.type = params.deviceTemplateType;
  }
  const res = await apiClient.get(path, { params: queryParams, responseType: 'blob' });
  return res;
}

async function importData(type: ImportExportType, file: File) {
  const importPaths: Record<ImportExportType, string> = {
    [ImportExportType.DEVICE]: '/devices/batch-import',
    [ImportExportType.CUSTOMER]: '/customers/batch-import',
    [ImportExportType.CABINET]: '/cabinets/batch-import'
  };
  const path = importPaths[type];
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post(path, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return res;
}

async function exportData(type: ImportExportType, params?: Record<string, unknown>) {
  const exportPaths: Record<ImportExportType, string> = {
    [ImportExportType.DEVICE]: '/devices/export',
    [ImportExportType.CUSTOMER]: '/customers/export',
    [ImportExportType.CABINET]: '/cabinets/export'
  };
  const path = exportPaths[type];
  const res = await apiClient.get(path, { params, responseType: 'blob' });
  return res;
}

export function useDownloadTemplate() {
  return useMutation({ mutationFn: downloadTemplate });
}

export function useImportData() {
  return useMutation({
    mutationFn: ({ type, file }: { type: ImportExportType; file: File }) => importData(type, file)
  });
}

export function useExportData() {
  return useMutation({
    mutationFn: ({ type, params }: { type: ImportExportType; params?: Record<string, unknown> }) =>
      exportData(type, params)
  });
}
