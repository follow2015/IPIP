/**
 * 开源软件授权页
 * 集中展示项目依赖的第三方库及其开源许可证，履行开源合规与透明义务。
 * 数据基于根目录 requirements.txt 与前端 package.json 的实际声明生成。
 */
import { Card, Tag, Typography, Space, Button, Tooltip } from 'antd';
import DataTable from '@/components/DataTable';
import { GithubOutlined, ExportOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

const { Title, Paragraph, Text, Link } = Typography;

type SettingsT = TFunction<'settings'>;
type CommonT = TFunction<'common'>;

type DepUsageKey =
  | 'license.dep.flask'
  | 'license.dep.flaskSqlalchemy'
  | 'license.dep.sqlalchemy'
  | 'license.dep.pyjwt'
  | 'license.dep.werkzeug'
  | 'license.dep.marshmallow'
  | 'license.dep.apispec'
  | 'license.dep.bcrypt'
  | 'license.dep.cryptography'
  | 'license.dep.flaskCors'
  | 'license.dep.pymysql'
  | 'license.dep.redis'
  | 'license.dep.netmiko'
  | 'license.dep.pysnmp'
  | 'license.dep.pyghmi'
  | 'license.dep.pandas'
  | 'license.dep.openpyxl'
  | 'license.dep.reportlab'
  | 'license.dep.textfsm'
  | 'license.dep.pyyaml'
  | 'license.dep.requests'
  | 'license.dep.qrcode'
  | 'license.dep.psutil'
  | 'license.dep.click'
  | 'license.dep.uvicorn'
  | 'license.dep.starlette'
  | 'license.dep.react'
  | 'license.dep.reactDom'
  | 'license.dep.reactRouterDom'
  | 'license.dep.antd'
  | 'license.dep.antDesignIcons'
  | 'license.dep.antDesignCharts'
  | 'license.dep.antvG6'
  | 'license.dep.tanstackQuery'
  | 'license.dep.axios'
  | 'license.dep.zustand'
  | 'license.dep.dayjs'
  | 'license.dep.ipaddrJs';

interface LicenseInfo {
  name: string;
  version: string;
  license: string;
  usage: DepUsageKey;
  homepage: string;
}

const backendDeps: LicenseInfo[] = [
  {
    name: 'Flask',
    version: '3.1.3',
    license: 'BSD-3-Clause',
    usage: 'license.dep.flask',
    homepage: 'https://github.com/pallets/flask'
  },
  {
    name: 'Flask-SQLAlchemy',
    version: '3.1.1',
    license: 'MIT',
    usage: 'license.dep.flaskSqlalchemy',
    homepage: 'https://github.com/pallets/flask-sqlalchemy'
  },
  {
    name: 'SQLAlchemy',
    version: '2.0.50',
    license: 'MIT',
    usage: 'license.dep.sqlalchemy',
    homepage: 'https://www.sqlalchemy.org'
  },
  {
    name: 'PyJWT',
    version: '2.10.1',
    license: 'MIT',
    usage: 'license.dep.pyjwt',
    homepage: 'https://github.com/jpadilla/pyjwt'
  },
  {
    name: 'Werkzeug',
    version: '3.1.8',
    license: 'BSD-3-Clause',
    usage: 'license.dep.werkzeug',
    homepage: 'https://github.com/pallets/werkzeug'
  },
  {
    name: 'marshmallow',
    version: '4.3.0',
    license: 'MIT',
    usage: 'license.dep.marshmallow',
    homepage: 'https://github.com/marshmallow-code/marshmallow'
  },
  {
    name: 'apispec',
    version: '6.10.0',
    license: 'MIT',
    usage: 'license.dep.apispec',
    homepage: 'https://github.com/marshmallow-code/apispec'
  },
  {
    name: 'bcrypt',
    version: '5.0.0',
    license: 'Apache-2.0',
    usage: 'license.dep.bcrypt',
    homepage: 'https://github.com/pyca/bcrypt'
  },
  {
    name: 'cryptography',
    version: '48.0.0',
    license: 'Apache-2.0 / BSD-3-Clause',
    usage: 'license.dep.cryptography',
    homepage: 'https://github.com/pyca/cryptography'
  },
  {
    name: 'flask-cors',
    version: '6.0.2',
    license: 'MIT',
    usage: 'license.dep.flaskCors',
    homepage: 'https://github.com/corydolphin/flask-cors'
  },
  {
    name: 'PyMySQL',
    version: '1.2.0',
    license: 'MIT',
    usage: 'license.dep.pymysql',
    homepage: 'https://github.com/PyMySQL/PyMySQL'
  },
  {
    name: 'redis',
    version: '8.0.0',
    license: 'MIT',
    usage: 'license.dep.redis',
    homepage: 'https://github.com/redis/redis-py'
  },
  {
    name: 'netmiko',
    version: '4.7.0',
    license: 'MIT',
    usage: 'license.dep.netmiko',
    homepage: 'https://github.com/ktbyers/netmiko'
  },
  {
    name: 'pysnmp',
    version: '7.1.27',
    license: 'BSD-2-Clause',
    usage: 'license.dep.pysnmp',
    homepage: 'https://github.com/etingof/pysnmp'
  },
  {
    name: 'pyghmi',
    version: '1.6.19',
    license: 'Apache-2.0',
    usage: 'license.dep.pyghmi',
    homepage: 'https://github.com/openstack/pyghmi'
  },
  {
    name: 'pandas',
    version: '3.0.3',
    license: 'BSD-3-Clause',
    usage: 'license.dep.pandas',
    homepage: 'https://pandas.pydata.org'
  },
  {
    name: 'openpyxl',
    version: '3.1.5',
    license: 'MIT',
    usage: 'license.dep.openpyxl',
    homepage: 'https://openpyxl.readthedocs.io'
  },
  {
    name: 'reportlab',
    version: '4.5.1',
    license: 'BSD-3-Clause',
    usage: 'license.dep.reportlab',
    homepage: 'https://www.reportlab.com'
  },
  {
    name: 'textfsm',
    version: '2.1.0',
    license: 'Apache-2.0',
    usage: 'license.dep.textfsm',
    homepage: 'https://github.com/google/textfsm'
  },
  {
    name: 'PyYAML',
    version: '6.0.3',
    license: 'MIT',
    usage: 'license.dep.pyyaml',
    homepage: 'https://github.com/yaml/pyyaml'
  },
  {
    name: 'requests',
    version: '2.34.2',
    license: 'Apache-2.0',
    usage: 'license.dep.requests',
    homepage: 'https://github.com/psf/requests'
  },
  {
    name: 'qrcode',
    version: '8.2',
    license: 'MIT',
    usage: 'license.dep.qrcode',
    homepage: 'https://github.com/lincolnloop/python-qrcode'
  },
  {
    name: 'psutil',
    version: '7.2.2',
    license: 'BSD-3-Clause',
    usage: 'license.dep.psutil',
    homepage: 'https://github.com/giampaolo/psutil'
  },
  {
    name: 'click',
    version: '8.4.1',
    license: 'BSD-3-Clause',
    usage: 'license.dep.click',
    homepage: 'https://github.com/pallets/click'
  },
  {
    name: 'uvicorn',
    version: '0.49.0',
    license: 'BSD-3-Clause',
    usage: 'license.dep.uvicorn',
    homepage: 'https://github.com/encode/uvicorn'
  },
  {
    name: 'starlette',
    version: '1.3.1',
    license: 'BSD-3-Clause',
    usage: 'license.dep.starlette',
    homepage: 'https://github.com/encode/starlette'
  }
];

const frontendDeps: LicenseInfo[] = [
  {
    name: 'react',
    version: '^19.2.5',
    license: 'MIT',
    usage: 'license.dep.react',
    homepage: 'https://github.com/facebook/react'
  },
  {
    name: 'react-dom',
    version: '^19.2.5',
    license: 'MIT',
    usage: 'license.dep.reactDom',
    homepage: 'https://github.com/facebook/react'
  },
  {
    name: 'react-router-dom',
    version: '^7.14.1',
    license: 'MIT',
    usage: 'license.dep.reactRouterDom',
    homepage: 'https://github.com/remix-run/react-router'
  },
  {
    name: 'antd',
    version: '^6.3.5',
    license: 'MIT',
    usage: 'license.dep.antd',
    homepage: 'https://github.com/ant-design/ant-design'
  },
  {
    name: '@ant-design/icons',
    version: '^6.1.1',
    license: 'MIT',
    usage: 'license.dep.antDesignIcons',
    homepage: 'https://github.com/ant-design/ant-design-icons'
  },
  {
    name: '@ant-design/charts',
    version: '^2.6.7',
    license: 'MIT',
    usage: 'license.dep.antDesignCharts',
    homepage: 'https://github.com/ant-design/ant-design-charts'
  },
  {
    name: '@antv/g6',
    version: '^5.1.1',
    license: 'MIT',
    usage: 'license.dep.antvG6',
    homepage: 'https://github.com/antvis/G6'
  },
  {
    name: '@tanstack/react-query',
    version: '^5.99.0',
    license: 'MIT',
    usage: 'license.dep.tanstackQuery',
    homepage: 'https://github.com/TanStack/query'
  },
  {
    name: 'axios',
    version: '^1.15.0',
    license: 'MIT',
    usage: 'license.dep.axios',
    homepage: 'https://github.com/axios/axios'
  },
  {
    name: 'zustand',
    version: '^5.0.12',
    license: 'MIT',
    usage: 'license.dep.zustand',
    homepage: 'https://github.com/pmndrs/zustand'
  },
  {
    name: 'dayjs',
    version: '^1.11.11',
    license: 'MIT',
    usage: 'license.dep.dayjs',
    homepage: 'https://github.com/iamkun/dayjs'
  },
  {
    name: 'ipaddr.js',
    version: '^2.2.0',
    license: 'MIT',
    usage: 'license.dep.ipaddrJs',
    homepage: 'https://github.com/whitequark/ipaddr.js'
  }
];

const licenseColor: Record<string, string> = {
  MIT: 'green',
  'BSD-3-Clause': 'blue',
  'BSD-2-Clause': 'blue',
  'Apache-2.0': 'purple',
  'Apache-2.0 / BSD-3-Clause': 'purple'
};

const renderCols = (s: SettingsT, c: CommonT, data: LicenseInfo[]) => [
  {
    title: s('license.column.component'),
    dataIndex: 'name',
    key: 'name',
    width: 200,
    render: (v: string) => <Text strong>{v}</Text>
  },
  {
    title: s('license.column.version'),
    dataIndex: 'version',
    key: 'version',
    width: 110,
    render: (v: string) => <Text code>{v}</Text>
  },
  {
    title: s('license.column.license'),
    dataIndex: 'license',
    key: 'license',
    width: 160,
    render: (v: string) => <Tag color={licenseColor[v] ?? 'default'}>{v}</Tag>
  },
  {
    title: s('license.column.usage'),
    dataIndex: 'usage',
    key: 'usage',
    render: (v: DepUsageKey) => s(v)
  },
  {
    title: c('field.source'),
    dataIndex: 'homepage',
    key: 'homepage',
    width: 90,
    render: (v: string) => (
      <Tooltip title={v}>
        <Button
          type="link"
          size="small"
          icon={<ExportOutlined />}
          href={v}
          target="_blank"
          rel="noopener noreferrer"
        >
          {c('action.view')}
        </Button>
      </Tooltip>
    )
  }
];

export default function LicensesPage() {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');

  return (
    <div style={{ padding: 24, maxWidth: 1080, margin: '0 auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            <GithubOutlined style={{ marginRight: 8 }} />
            {t('license.pageTitle')}
          </Title>
          <Paragraph type="secondary">
            {t('license.introPart1')}
            <Text code>requirements.txt</Text>
            {t('license.introPart2')}
            <Text code>package.json</Text>
            {t('license.introPart3')}
          </Paragraph>
        </div>

        <Card
          title={t('license.selfTitle')}
          size="small"
          style={{ borderColor: '#1677ff' }}
          extra={
            <Button
              type="link"
              size="small"
              icon={<ExportOutlined />}
              href="https://www.apache.org/licenses/LICENSE-2.0"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t('license.selfFullText')}
            </Button>
          }
        >
          <Paragraph style={{ marginBottom: 8 }}>
            <Tag color="purple">Apache License 2.0</Tag>
            {t('license.selfSummary')}
          </Paragraph>
          <Paragraph style={{ marginBottom: 0 }}>
            {t('license.selfTermsPart1')}
            <Text code>LICENSE</Text>
            {t('license.selfTermsPart2')}
          </Paragraph>
        </Card>

        <Card title={t('license.backendDepsTitle')} size="small">
          <DataTable<LicenseInfo>
            columns={renderCols(t, tc, backendDeps)}
            dataSource={backendDeps}
            rowKey="name"
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
            showCard={false}
            searchable={false}
          />
        </Card>

        <Card title={t('license.frontendDepsTitle')} size="small">
          <DataTable<LicenseInfo>
            columns={renderCols(t, tc, frontendDeps)}
            dataSource={frontendDeps}
            rowKey="name"
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
            showCard={false}
            searchable={false}
          />
        </Card>

        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          {t('license.footerNote')}
        </Paragraph>
      </Space>
    </div>
  );
}
