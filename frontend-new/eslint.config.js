import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

/**
 * ESLint Flat Config（ESLint 10 原生格式）
 *
 * 说明：项目原使用 .eslintrc.cjs，但 ESLint 9+ 默认只认 flat config，
 * 旧配置在 ESLint 10 下完全不生效（lint 命令空转）。本文件为等价迁移，
 * 并补充了测试文件 / 配置文件的豁免规则（P0 工程化门禁的一部分）。
 */

// Node 全局（供 vite.config.ts / vitest.config.ts 等构建配置文件使用）
const nodeGlobals = {
  __dirname: 'readonly',
  __filename: 'readonly',
  process: 'readonly',
  console: 'readonly',
  module: 'readonly',
  require: 'readonly',
  global: 'readonly',
  URL: 'readonly',
  URLSearchParams: 'readonly'
};

/**
 * 移动端布局门禁 —— ESQuery selector 常量（B0）
 *
 * 实现方式：`no-restricted-syntax`（ESLint 内建）+ ESQuery selector，**零新依赖**。
 * 5 条规则的 selector 均经 esquery@1.7.0 + @typescript-eslint/parser 实测命中。
 *
 * [WARN] 关键：单条 selector 由 JSX 元素名匹配时，<Space.Compact> 是 JSXMemberExpression，
 * `name.name` 不是字符串化的 "Space.Compact"，必须用 :matches 双分支匹配 name.property.name。
 * （B0 复核实测：原 selector `[name.name=/^(Space|Space\.Compact)$/]` 对 member expression 静默漏报 0 命中。）
 */
const LAYOUT_GATE_SELECTORS = {
  'no-bare-space': {
    // 裸 <Space> / <Space.Compact>（缺 wrap prop）
    selector:
      ':matches(JSXOpeningElement[name.name=/^Space$/], JSXOpeningElement[name.property.name="Compact"]):not(:has(JSXAttribute[name.name="wrap"]))',
    message:
      '裸 <Space> 在窄屏不折行会把内容顶宽致横向溢出。请加 wrap（<Space wrap>），或改用 ' +
      '@/components/responsive 的布局原语（DetailActionBar / FilterBar）。'
  },
  'no-raw-flex-toolbar': {
    // 同一 ObjectExpression 里同时出现 display:'flex' 与 justifyContent:'space-between'
    selector:
      'ObjectExpression > Property[key.name="display"][value.value="flex"] ~ Property[key.name="justifyContent"][value.value="space-between"]',
    message:
      '手写 display:flex + space-between 的工具栏在窄屏不折行。请改用 ' +
      '@/components/responsive 的 DetailActionBar / FilterBar / DataTable 工具栏。'
  },
  // 注：`no-adhoc-overflow` 已**移出**本表，改由下方本地规则 `ipip/no-adhoc-overflow` 承载。
  // 原因见该文件末尾规则实现处的说明 —— 它需要读注释判断豁免，ESQuery selector 做不到。
  'no-fixed-width-control': {
    // width/minWidth/maxWidth 上写字面量（JSX）或 Literal（对象属性）
    selector:
      ':matches(Property[key.name=/^(width|minWidth|maxWidth)$/][value.type="Literal"], JSXAttribute[name.name=/^(width|minWidth|maxWidth)$/] JSXExpressionContainer Literal)',
    message:
      '筛选控件的固定宽度在窄屏会溢出。请走 FilterBar 的 width prop（移动端自动转 100%），' +
      '或用相对值（% / flex）。'
  },
  'no-segmented-in-toolbar': {
    // <Toolbar 类组件> 内部嵌 <Segmented>
    selector:
      'JSXElement[openingElement.name.name=/^(PageToolbar|FilterBar|Toolbar)$/] JSXElement[openingElement.name.name="Segmented"]',
    message:
      'Segmented 不是滚动容器（@rc-component/segmented 无 overflow 规则），放在工具栏里窄屏会被裁切。' +
      '请改用 @/components/responsive 的 <SegmentedResponsive>。'
  }
};

/**
 * 存量 adhoc overflow 文件清单（B0 快照，`node scripts/layout-ratchet.mjs --print-exempt` 可复现）。
 * B0 不在此做文件级豁免（规则整体为 warn）；本清单供 B2/B3/B4 分批清理时对照，
 * 每清完一个就删一行，清空即该维度可升 error。
 *
 * 当前 23 个文件（2026-10-07 实测）：
 *   components: AuditLogTable, Layout/Sidebar, Notification/NotificationBell,
 *     PortMemberBlocks, RoomLayout/{CabinetNode,ChannelLayer,RoomLayout},
 *     UPositionSelector/{DetailPanel,DeviceBlock,NodeGrid,NodeList,RackBody,SidePanel}
 *   pages: AI/AIMonitor, Dashboard, Devices/DeviceDetail/ConfigTab,
 *     Devices/DeviceDetail/UnifiedPortTab/PortBatchAddModal, IP/IPAudit,
 *     Monitor/Alerts, Monitor/NocScreen, Switches/PortDetailModal,
 *     Topology/TopologyGraph/TopologyGraph, Topology/index
 */

/**
 * 5 条移动端布局门禁合并为**一条** `no-restricted-syntax`：其配置是
 * { selector, message } 的数组（ESLint 内建规则的标准用法）。
 *
 * [WARN] B0 阶段严重级 = **warn**，不是 error。
 *   原因（B0 实测）：存量远超预期 —— 裸 <Space> 228 处、固定宽 width 字面量 758 处、
 *   adhoc overflow 41 处，分布在数十个业务文件里。若 B0 就设 error，
 *   等于要求"同一批里把存量全清完"，违背 B0「纯新增、业务文件零改动」的定位。
 *   故 B0 一律 warn：信号存在、不阻断 CI；升 error 是 B2/B3/B4 分批清理后的事。
 *
 * 退出路径：每清完一类存量 → 把该 selector 从本数组移入下面的 ERROR 数组 → 逐步收紧。
 */
const layoutGateRule = [
  'warn',
  ...Object.entries(LAYOUT_GATE_SELECTORS).map(([id, { selector, message }]) => ({
    selector,
    message: `[ipip/${id}] ${message}`
  }))
];

/**
 * B4（ADR-007 落地）：`ipip/no-adhoc-overflow` —— 能读注释的本地规则
 *
 * 为什么不能继续用 `no-restricted-syntax` + ESQuery selector：
 *   ADR-007 写明「规则以**是否带 `[OVERFLOW-EXEMPT]` 注释**作为放行判据」，
 *   但 ESQuery 只作用于 **AST**，注释不在 AST 里 —— 该判据从未真正生效，
 *   全仓 `[OVERFLOW-EXEMPT]` 标记数长期为 0。豁免没有牙 = 登记了也没有约束力。
 *   故本条改用自定义规则：命中 overflow* 后回读源码注释，命中标记即放行。
 *
 * 判定"注释是否属于该节点"：
 *   - 前置：注释结束位置在节点之前，且**结束行 >= 节点起始行 - 1**
 *     （同行的行尾注释、或紧邻上一行的独立注释都算；隔了 2 行以上不算）
 *   - 后置：与节点**同一行**且位于节点之后（行尾注释）
 *   刻意不做"文件级"或"函数级"豁免：ADR-007 要求逐处写理由，理由必须挨着代码。
 *
 * 与 `scripts/layout-ratchet.mjs` 的分工：ratchet 按正则扫源码、统计**文件数**
 * （不认注释）；本规则认注释、统计**未写理由的处数**。两者互补 ——
 * ratchet 防"文件变多"，本规则防"新增一处不写理由"。
 */
const OVERFLOW_EXEMPT_MARKER = '[OVERFLOW-EXEMPT]';
const OVERFLOW_KEY_RE = /^overflow(X|Y)?$/;

const overflowGateRule = {
  meta: {
    type: 'suggestion',
    docs: {
      description: '禁止手写 overflow（含 X/Y）；功能性裁剪须以 [OVERFLOW-EXEMPT] 注释写明理由'
    },
    schema: []
  },
  create(context) {
    const sourceCode = context.sourceCode ?? context.getSourceCode();

    const comments = sourceCode.getAllComments();
    /**
     * 放行判据：紧邻处存在含 [OVERFLOW-EMPT] 标记的注释。
     *
     * [B5 修订，2026-10-08] 支持**连续多行 // 注释**：理由往往一行写不下，而多行
     * `//` 在 ESLint 里是**多个独立注释** —— 标记若写在首行，首行距属性可能已超过
     * 1 行，判据会失效（B4 登记的 36 处多为单行注释，故未暴露）。
     * 这里把行号连续的注释合并成一个「注释块」，用块的**结束行**做紧邻判定：
     *   - 多行块、标记在任意行 → 块结束行紧邻即放行
     *   - 标记与属性之间隔了空行/代码 → 块结束行不紧邻 → 仍告警（不过松）
     */
    const hasExemptMarker = (node) =>
      comments.some((c, i) => {
        if (!c.loc || !c.value.includes(OVERFLOW_EXEMPT_MARKER)) return false;
        let endLine = c.loc.end.line;
        let endRange = c.range[1];
        for (let j = i + 1; j < comments.length; j += 1) {
          const nx = comments[j];
          if (!nx.loc || nx.loc.start.line > endLine + 1) break;
          endLine = Math.max(endLine, nx.loc.end.line);
          endRange = nx.range[1];
        }
        const beforeNode = endRange <= node.range[0] && endLine >= node.loc.start.line - 1;
        const sameLineAfter = c.loc.start.line === node.loc.end.line && c.range[0] >= node.range[1];
        return beforeNode || sameLineAfter;
      });

    const check = (node) => {
      if (hasExemptMarker(node)) return;
      context.report({
        node,
        message:
          '[ipip/no-adhoc-overflow] 禁止手写 overflow（含 X/Y）。横向滚动请用 ' +
          '@/components/responsive 的 <ScrollX reason="...">；已知安全的裁剪请集中到 ' +
          'src/styles/overflow.css。若此处确属**功能性裁剪**（元素本身是固定尺寸可视块，' +
          '如 U 位格子 / 机柜格子 / 限高滚动块 / 圆角裁剪），请在紧邻处加 ' +
          '`[OVERFLOW-EXEMPT]` 注释写明理由 —— 无理由的豁免一律视为技术债。'
      });
    };

    return {
      Property(node) {
        const k = node.key;
        const name =
          k?.type === 'Identifier' ? k.name : k?.type === 'Literal' ? String(k.value) : '';
        if (OVERFLOW_KEY_RE.test(name)) check(node);
      },
      JSXAttribute(node) {
        if (node.name?.type === 'JSXIdentifier' && OVERFLOW_KEY_RE.test(node.name.name))
          check(node);
      }
    };
  }
};

/** 本地插件：承载需要读注释 / 需要跨节点上下文的门禁规则 */
const ipipPlugin = { rules: { 'no-adhoc-overflow': overflowGateRule } };

export default tseslint.config(
  {
    // 生成物不参与 lint。
    // 生成器 scripts/generate_frontend_enums.py 已存在并接线（`make sync-enums`），
    // 与后端 app/core/enums.py STATUS_DISPLAY 的漂移由 tests/test_frontend_enum_drift.py 守住，
    // 不再是"双真相源、改动需两侧手工同步"。
    // （旧注释称"脚本在仓库中不存在"，系 2026-09-16 核实结论，2026-10-02 复核已更正。）
    // 类型安全由 tsc 保障（tsc 不读 eslint ignores）。
    ignores: [
      'dist',
      'coverage',
      'node_modules',
      'src/types/api-generated.ts',
      'src/types/status-codes.generated.ts'
    ]
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true }
      }
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      ipip: ipipPlugin
    },
    rules: {
      // 禁止 any 类型：存量代码有约 47 处 any（含 G6 拓扑图回调），
      // 统一降为 warning 作为技术债标记，待专项清理后再升为 error
      '@typescript-eslint/no-explicit-any': 'warn',
      // 禁止 window 全局变量（有意的兜底场景用 eslint-disable 标注）
      'no-restricted-globals': ['error', 'window'],
      // 未使用变量/参数：降级为 warning，与 tsconfig 中 noUnusedLocals:false 保持一致
      // （存量代码有约 197 处未使用导入/变量，需后续清理后再升为 error）
      // varsIgnorePattern/argsIgnorePattern: 允许 `_` 前缀的占位（如 rest 解构 `{ key: _k, ...r }`），
      // 配合 ignoreRestSiblings 根治"为绕过 no-unused-vars 而散落的 eslint-disable"问题（见 N1）。
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { varsIgnorePattern: '^_', argsIgnorePattern: '^_', ignoreRestSiblings: true }
      ],
      // React Hooks 规则（等价 plugin:react-hooks/recommended）
      // 原为 warn：存量 Detail 页 early-return 后再调用 Hook 会导致
      // "Rendered more hooks than during the previous render" 偶发整页崩溃。
      // 2026-07-22 已清零全部 41 处违规，升级为 error 纳入 CI 门禁，防止回归。
      'react-hooks/rules-of-hooks': 'error',
      // 与 rules-of-hooks 同一处理路径：先专项清零、再升级纳入 CI 门禁防回归。
      // 2026-09-30 清零最后 10 处 —— disclosure 对象解构成稳定函数、兜底字面量（?? [] / ?? {...}）
      // 收敛为 useMemo、事件回调与翻译函数改用 ref 持有、依赖数组里的函数调用提取为变量。
      'react-hooks/exhaustive-deps': 'error',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // 无副作用的表达式（如裸函数调用）保持 error
      'no-unused-expressions': 'error',
      /**
       * 移动端布局门禁（B0）：5 条 ESQuery selector 合并为一条 no-restricted-syntax。
       * 存量文件在下方 override 块降为 warn（保留信号、不阻断 CI）。
       * 退出条件：B2/B3/B4 逐条清理后，从 LAYOUT_RATCHET_EXEMPT 删除，清空即全 error。
       */
      'no-restricted-syntax': layoutGateRule,
      // B4：overflow 门禁改由本地规则承载（需读 `[OVERFLOW-EXEMPT]` 注释，selector 做不到）
      'ipip/no-adhoc-overflow': 'warn',
      // 禁止回退到 antd 已废弃的 List（antd 6.6.2 起标记 deprecated，下个大版本移除）。
      // 全仓已于 2026-10-06 迁移到 Listy（见 docs/plan/2026-10-06-Listy迁移-实施计划.md），
      // 此规则防止后续新增代码重新引入。
      // 注意只匹配 'List' 具名导入：'Listy' 与 'Form.List'（表单能力，非列表组件）不受影响。
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'antd',
              importNames: ['List'],
              message:
                'antd 的 List 已废弃（6.6.2 标记 deprecated，下个大版本移除），请改用 Listy。' +
                '注意两者 API 不同：dataSource→items、renderItem→itemRender、' +
                'rowKey 类型必填且只接收 item、无 split/locale/loading/size、' +
                '无 List.Item/List.Item.Meta 子元素结构。迁移参考：docs/plan/2026-10-06-Listy迁移-实施计划.md'
            }
          ]
        }
      ]
    }
  },
  // 测试文件：允许 any（mock 类型宽松）与 window（jsdom 环境），关闭组件导出限制
  {
    files: ['**/*.test.ts', '**/*.test.tsx', '**/*.spec.ts', '**/*.spec.tsx', 'src/test/**/*'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-restricted-globals': 'off',
      'react-refresh/only-export-components': 'off'
    }
  },
  // 布局原语自身：它们是"正解"，不是"债"——豁免布局门禁
  {
    files: ['src/components/responsive/**'],
    rules: { 'no-restricted-syntax': 'off', 'ipip/no-adhoc-overflow': 'off' }
  },
  // 构建 / 测试配置文件 + scripts 下的 node 脚本：提供 node 全局（__dirname / process 等）
  {
    files: [
      '*.config.ts',
      '*.config.js',
      '*.config.cjs',
      '*.config.mjs',
      'vitest.config.ts',
      'vite.config.ts',
      'scripts/**/*.mjs',
      'scripts/**/*.js',
      'scripts/**/*.cjs'
    ],
    languageOptions: { globals: nodeGlobals }
  }
);
