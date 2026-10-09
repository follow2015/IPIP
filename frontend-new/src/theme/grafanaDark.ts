import { theme } from 'antd';
import type { MappingAlgorithm } from 'antd';

export const GRAFANA_DARK_SEED = {
  colorPrimary: '#63aaff',
  colorInfo: '#63aaff',
  colorSuccess: '#84dd78',
  colorWarning: '#ffff2e',
  colorError: '#ff5269'
};

export const GRAFANA_DARK_OVERRIDE = {
  colorPrimary: '#5794f2',
  colorInfo: '#5794f2',
  colorSuccess: '#73bf69',
  colorWarning: '#fade2a',
  colorError: '#f2495c',
  colorBgLayout: '#111217',
  colorBgContainer: '#181b1f',
  colorBgElevated: '#1f2328'
};

export const grafanaDarkAlgorithm: MappingAlgorithm = (seed, map) => ({
  ...theme.darkAlgorithm(seed, map),
  ...GRAFANA_DARK_OVERRIDE
});
