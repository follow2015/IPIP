/**
 * 开源软件授权页
 * 集中展示项目依赖的第三方库及其开源许可证，履行开源合规与透明义务。
 * 数据基于根目录 requirements.txt 与前端 package.json 的实际声明生成。
 */
import { Card, Table, Tag, Typography, Space, Button, Tooltip } from 'antd';
import { GithubOutlined, ExportOutlined } from '@ant-design/icons';

const { Title, Paragraph, Text, Link } = Typography;

interface LicenseInfo {
  name: string;
  version: string;
  license: string;
  usage: string;
  homepage: string;
}

const backendDeps: LicenseInfo[] = [
  {
    name: 'Flask',
    version: '3.1.3',
    license: 'BSD-3-Clause',
    usage: 'Web 框架（应用工厂、路由、中间件）',
    homepage: 'https://github.com/pallets/flask'
  },
  {
    name: 'Flask-SQLAlchemy',
    version: '3.1.1',
    license: 'MIT',
    usage: 'ORM 集成',
    homepage: 'https://github.com/pallets/flask-sqlalchemy'
  },
  {
    name: 'SQLAlchemy',
    version: '2.0.50',
    license: 'MIT',
    usage: 'SQL 工具包与 ORM',
    homepage: 'https://www.sqlalchemy.org'
  },
  {
    name: 'PyJWT',
    version: '2.10.1',
    license: 'MIT',
    usage: 'JWT 签发与校验',
    homepage: 'https://github.com/jpadilla/pyjwt'
  },
  {
    name: 'Werkzeug',
    version: '3.1.8',
    license: 'BSD-3-Clause',
    usage: 'WSGI 工具库',
    homepage: 'https://github.com/pallets/werkzeug'
  },
  {
    name: 'marshmallow',
    version: '4.3.0',
    license: 'MIT',
    usage: '请求/响应数据序列化与校验',
    homepage: 'https://github.com/marshmallow-code/marshmallow'
  },
  {
    name: 'apispec',
    version: '6.10.0',
    license: 'MIT',
    usage: 'OpenAPI 规范生成',
    homepage: 'https://github.com/marshmallow-code/apispec'
  },
  {
    name: 'bcrypt',
    version: '5.0.0',
    license: 'Apache-2.0',
    usage: '密码哈希',
    homepage: 'https://github.com/pyca/bcrypt'
  },
  {
    name: 'cryptography',
    version: '48.0.0',
    license: 'Apache-2.0 / BSD-3-Clause',
    usage: '敏感配置加密',
    homepage: 'https://github.com/pyca/cryptography'
  },
  {
    name: 'flask-cors',
    version: '6.0.2',
    license: 'MIT',
    usage: '跨域资源共享支持',
    homepage: 'https://github.com/corydolphin/flask-cors'
  },
  {
    name: 'PyMySQL',
    version: '1.2.0',
    license: 'MIT',
    usage: 'MySQL 驱动',
    homepage: 'https://github.com/PyMySQL/PyMySQL'
  },
  {
    name: 'redis',
    version: '8.0.0',
    license: 'MIT',
    usage: '缓存 / 告警 outbox / 实时网关',
    homepage: 'https://github.com/redis/redis-py'
  },
  {
    name: 'netmiko',
    version: '4.7.0',
    license: 'MIT',
    usage: '网络设备 SSH/Telnet 自动化',
    homepage: 'https://github.com/ktbyers/netmiko'
  },
  {
    name: 'pysnmp',
    version: '7.1.27',
    license: 'BSD-2-Clause',
    usage: 'SNMP 设备指标采集',
    homepage: 'https://github.com/etingof/pysnmp'
  },
  {
    name: 'pyghmi',
    version: '1.6.19',
    license: 'Apache-2.0',
    usage: 'BMC/IPMI 管理',
    homepage: 'https://github.com/openstack/pyghmi'
  },
  {
    name: 'pandas',
    version: '3.0.3',
    license: 'BSD-3-Clause',
    usage: 'Excel 导入导出数据处理',
    homepage: 'https://pandas.pydata.org'
  },
  {
    name: 'openpyxl',
    version: '3.1.5',
    license: 'MIT',
    usage: 'Excel 文件读写',
    homepage: 'https://openpyxl.readthedocs.io'
  },
  {
    name: 'reportlab',
    version: '4.5.1',
    license: 'BSD-3-Clause',
    usage: '客户终止存档 PDF 生成',
    homepage: 'https://www.reportlab.com'
  },
  {
    name: 'textfsm',
    version: '2.1.0',
    license: 'Apache-2.0',
    usage: '网络设备回显文本解析',
    homepage: 'https://github.com/google/textfsm'
  },
  {
    name: 'PyYAML',
    version: '6.0.3',
    license: 'MIT',
    usage: '配置文件 / 种子数据解析',
    homepage: 'https://github.com/yaml/pyyaml'
  },
  {
    name: 'requests',
    version: '2.34.2',
    license: 'Apache-2.0',
    usage: 'HTTP 客户端（Webhook 投递）',
    homepage: 'https://github.com/psf/requests'
  },
  {
    name: 'qrcode',
    version: '8.2',
    license: 'MIT',
    usage: '二维码生成',
    homepage: 'https://github.com/lincolnloop/python-qrcode'
  },
  {
    name: 'psutil',
    version: '7.2.2',
    license: 'BSD-3-Clause',
    usage: '主机资源指标采集',
    homepage: 'https://github.com/giampaolo/psutil'
  },
  {
    name: 'click',
    version: '8.4.1',
    license: 'BSD-3-Clause',
    usage: 'Flask CLI 命令',
    homepage: 'https://github.com/pallets/click'
  },
  {
    name: 'uvicorn',
    version: '0.49.0',
    license: 'BSD-3-Clause',
    usage: '实时网关 ASGI 服务器',
    homepage: 'https://github.com/encode/uvicorn'
  },
  {
    name: 'starlette',
    version: '1.3.1',
    license: 'BSD-3-Clause',
    usage: '实时网关 Web 框架',
    homepage: 'https://github.com/encode/starlette'
  }
];

const frontendDeps: LicenseInfo[] = [
  {
    name: 'react',
    version: '^19.2.5',
    license: 'MIT',
    usage: 'UI 视图层框架',
    homepage: 'https://github.com/facebook/react'
  },
  {
    name: 'react-dom',
    version: '^19.2.5',
    license: 'MIT',
    usage: 'React DOM 渲染',
    homepage: 'https://github.com/facebook/react'
  },
  {
    name: 'react-router-dom',
    version: '^7.14.1',
    license: 'MIT',
    usage: '前端路由',
    homepage: 'https://github.com/remix-run/react-router'
  },
  {
    name: 'antd',
    version: '^6.3.5',
    license: 'MIT',
    usage: '企业级 UI 组件库',
    homepage: 'https://github.com/ant-design/ant-design'
  },
  {
    name: '@ant-design/icons',
    version: '^6.1.1',
    license: 'MIT',
    usage: '图标资源',
    homepage: 'https://github.com/ant-design/ant-design-icons'
  },
  {
    name: '@ant-design/charts',
    version: '^2.6.7',
    license: 'MIT',
    usage: '图表可视化',
    homepage: 'https://github.com/ant-design/ant-design-charts'
  },
  {
    name: '@antv/g6',
    version: '^5.1.1',
    license: 'MIT',
    usage: '拓扑图渲染',
    homepage: 'https://github.com/antvis/G6'
  },
  {
    name: '@tanstack/react-query',
    version: '^5.99.0',
    license: 'MIT',
    usage: '服务端状态管理',
    homepage: 'https://github.com/TanStack/query'
  },
  {
    name: 'axios',
    version: '^1.15.0',
    license: 'MIT',
    usage: 'HTTP 请求客户端',
    homepage: 'https://github.com/axios/axios'
  },
  {
    name: 'zustand',
    version: '^5.0.12',
    license: 'MIT',
    usage: '轻量状态管理',
    homepage: 'https://github.com/pmndrs/zustand'
  },
  {
    name: 'dayjs',
    version: '^1.11.11',
    license: 'MIT',
    usage: '日期时间处理',
    homepage: 'https://github.com/iamkun/dayjs'
  },
  {
    name: 'ipaddr.js',
    version: '^2.2.0',
    license: 'MIT',
    usage: 'IP 地址解析与计算',
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

const renderCols = (data: LicenseInfo[]) => [
  {
    title: '组件',
    dataIndex: 'name',
    key: 'name',
    width: 200,
    render: (v: string) => <Text strong>{v}</Text>
  },
  {
    title: '版本',
    dataIndex: 'version',
    key: 'version',
    width: 110,
    render: (v: string) => <Text code>{v}</Text>
  },
  {
    title: '许可证',
    dataIndex: 'license',
    key: 'license',
    width: 160,
    render: (v: string) => <Tag color={licenseColor[v] ?? 'default'}>{v}</Tag>
  },
  { title: '用途', dataIndex: 'usage', key: 'usage' },
  {
    title: '来源',
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
          查看
        </Button>
      </Tooltip>
    )
  }
];

export default function LicensesPage() {
  return (
    <div style={{ padding: 24, maxWidth: 1080, margin: '0 auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            <GithubOutlined style={{ marginRight: 8 }} />
            开源软件授权
          </Title>
          <Paragraph type="secondary">
            本页面说明两件事：本项目的自身授权条款，以及本项目所依赖的第三方开源组件及其许可证。
            依赖与版本依据后端 <Text code>requirements.txt</Text> 与前端{' '}
            <Text code>package.json</Text> 的实际声明生成。
          </Paragraph>
        </div>

        <Card
          title="本项目授权"
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
              完整文本
            </Button>
          }
        >
          <Paragraph style={{ marginBottom: 8 }}>
            <Tag color="purple">Apache License 2.0</Tag>
            本项目（ipip）源代码以 Apache-2.0 许可证发布。
          </Paragraph>
          <Paragraph style={{ marginBottom: 0 }}>
            该许可证允许自由使用、修改、分发与商业化，并附带明确的专利授权与署名义务，适合后续商业化或接受捐赠的场景。
            您可自由将其用于商业用途，但须保留版权声明并附上许可证副本；若修改文件须显著标注变更。
            完整条款见仓库根目录 <Text code>LICENSE</Text> 文件。
          </Paragraph>
        </Card>

        <Card title="第三方依赖（后端 / Python）" size="small">
          <Table<LicenseInfo>
            columns={renderCols(backendDeps)}
            dataSource={backendDeps}
            rowKey="name"
            pagination={false}
            size="middle"
          />
        </Card>

        <Card title="第三方依赖（前端 / Node.js）" size="small">
          <Table<LicenseInfo>
            columns={renderCols(frontendDeps)}
            dataSource={frontendDeps}
            rowKey="name"
            pagination={false}
            size="middle"
          />
        </Card>

        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          开发期构建工具（Vite、TypeScript、ESLint、Vitest 等）未在此列出；如需完整
          SBOM，请参考各依赖清单文件。
        </Paragraph>
      </Space>
    </div>
  );
}
