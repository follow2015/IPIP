#!/usr/bin/env node


import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ts = require('typescript');

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, '..');

const cliArgs = process.argv.slice(2);
const STATIC_ONLY = cliArgs.includes('--static-only');
const STRICT = cliArgs.includes('--strict');
const positional = cliArgs.filter((a) => !a.startsWith('--'));
const rootDir = resolve(projectRoot, positional[0] || 'src');
const tsconfigPath = resolve(projectRoot, positional[1] || 'tsconfig.json');


function stripJsonComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\
    .replace(/(^|[^:])\/\/.*$/gm, '$1'); 
}
const tsconfig = JSON.parse(stripJsonComments(readFileSync(tsconfigPath, 'utf8')));
const compilerOptions = tsconfig.compilerOptions || {};
const baseUrl = compilerOptions.baseUrl
  ? resolve(projectRoot, compilerOptions.baseUrl)
  : projectRoot;
const paths = compilerOptions.paths || {};

const aliasMatchers = Object.entries(paths).map(([pattern, targets]) => {
  const [prefix, suffix] = pattern.split('*');
  return { prefix, suffix: suffix || '', targets: targets.map((t) => t.replace('*', '')) };
});

const EXTENSIONS = ['.ts', '.tsx', '.mts', '.cts', '.d.ts'];

function tryExtensions(p) {
  if (statSync(p, { throwIfNoEntry: false })) {
    if (statSync(p).isFile()) return p;
  }
  for (const ext of EXTENSIONS) {
    const cand = p + ext;
    if (statSync(cand, { throwIfNoEntry: false })) return cand;
  }
  for (const ext of EXTENSIONS) {
    const cand = join(p, 'index' + ext);
    if (statSync(cand, { throwIfNoEntry: false })) return cand;
  }
  return null;
}

function resolveAlias(specifier) {
  for (const m of aliasMatchers) {
    if (specifier.startsWith(m.prefix) && specifier.endsWith(m.suffix)) {
      const rest = m.suffix
        ? specifier.slice(m.prefix.length, -m.suffix.length)
        : specifier.slice(m.prefix.length);
      for (const t of m.targets) {
        const resolved = tryExtensions(join(baseUrl, t + rest));
        if (resolved) return resolved;
      }
    }
  }
  return null;
}

function resolveImport(specifier, fromFile) {
  if (aliasMatchers.some((m) => specifier.startsWith(m.prefix))) {
    return resolveAlias(specifier);
  }
  if (specifier.startsWith('.') || specifier.startsWith('/')) {
    const base = specifier.startsWith('/')
      ? resolve(projectRoot, specifier.slice(1))
      : resolve(dirname(fromFile), specifier);
    return tryExtensions(base);
  }
  return null; 
}


function collectFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
      out.push(...collectFiles(full));
    } else if (/\.(ts|tsx|mts|cts)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      out.push(full);
    }
  }
  return out;
}

const files = collectFiles(rootDir);
const fileSet = new Set(files);


const graph = new Map(); 
for (const file of files) {
  const src = readFileSync(file, 'utf8');
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.ES2020, true, ts.ScriptKind.TSX);
  const edges = new Map(); 
  const addEdge = (target, type) => {
    if (!edges.has(target)) edges.set(target, type);
    
    else if (edges.get(target) === 'lazy' && type === 'strong') edges.set(target, type);
  };
  const visit = (node) => {
    if (ts.isImportDeclaration(node) && node.moduleSpecifier && !node.importClause?.isTypeOnly) {
      const target = resolveImport(node.moduleSpecifier.text, file);
      if (target && fileSet.has(target)) addEdge(target, 'strong');
    }
    if (ts.isExportDeclaration(node) && node.moduleSpecifier && !node.isTypeOnly) {
      const target = resolveImport(node.moduleSpecifier.text, file);
      if (target && fileSet.has(target)) addEdge(target, 'strong');
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  
  
  if (!STATIC_ONLY) {
    const dynamicRe = /(?:import\(|=>\s*import\()\s*['"]([^'"]+)['"]\s*\)/g;
    let dm;
    while ((dm = dynamicRe.exec(src))) {
      const target = resolveImport(dm[1], file);
      if (target && fileSet.has(target)) addEdge(target, 'lazy');
    }
  }
  graph.set(file, edges);
}


const adjList = new Map();
for (const [file, edges] of graph) {
  adjList.set(file, [...edges.keys()]);
}

function tarjanSCC(g) {
  let index = 0;
  const stack = [];
  const onStack = new Set();
  const indices = new Map();
  const lowlink = new Map();
  const sccs = [];

  function strongconnect(v) {
    indices.set(v, index);
    lowlink.set(v, index);
    index++;
    stack.push(v);
    onStack.add(v);
    for (const w of g.get(v) || []) {
      if (!indices.has(w)) {
        strongconnect(w);
        lowlink.set(v, Math.min(lowlink.get(v), lowlink.get(w)));
      } else if (onStack.has(w)) {
        lowlink.set(v, Math.min(lowlink.get(v), indices.get(w)));
      }
    }
    if (lowlink.get(v) === indices.get(v)) {
      const comp = [];
      let w;
      do {
        w = stack.pop();
        onStack.delete(w);
        comp.push(w);
      } while (w !== v);
      sccs.push(comp);
    }
  }

  for (const v of g.keys()) if (!indices.has(v)) strongconnect(v);
  return sccs;
}


function enumerateCycles(sccNodes) {
  const nodeSet = new Set(sccNodes);
  const localGraph = new Map();
  for (const n of sccNodes) {
    const edges = graph.get(n) || new Map();
    localGraph.set(n, [...edges.entries()].filter(([t]) => nodeSet.has(t)));
  }
  const seen = new Set();
  const list = [];
  const path = [];

  const canonical = (cycle) => {
    const min = cycle.reduce((a, b) => (a < b ? a : b));
    const idx = cycle.indexOf(min);
    return [...cycle.slice(idx), ...cycle.slice(0, idx)].join(' -> ');
  };

  function dfs(start, v) {
    path.push(v);
    for (const [w] of localGraph.get(v) || []) {
      if (w === start && path.length >= 2) {
        const key = canonical(path);
        if (!seen.has(key)) {
          seen.add(key);
          
          const cycleEdgeTypes = [];
          for (let i = 0; i < path.length; i++) {
            const from = path[i];
            const to = path[(i + 1) % path.length];
            cycleEdgeTypes.push(graph.get(from)?.get(to) || 'strong');
          }
          const severity = cycleEdgeTypes.every(t => t === 'strong') ? 'strong' : 'lazy';
          list.push({ nodes: [...path], severity, lazyEdges: cycleEdgeTypes.filter(t => t === 'lazy').length });
        }
      } else if (!path.includes(w)) {
        dfs(start, w);
      }
    }
    path.pop();
  }

  for (const n of sccNodes) dfs(n, n);
  return list;
}


const rel = (p) => p.replace(projectRoot + '/', '');
const sccs = tarjanSCC(adjList);
const cyclic = sccs.filter((c) => c.length > 1);


if (process.env.DEBUG) {
  for (const [f, edges] of graph) {
    if (/api-client|stores\/auth|router\/index|services\/auth|router\/guards|router\/route/.test(f)) {
      console.error(rel(f), '=>', [...edges.entries()].map(([t, type]) => `${rel(t)}(${type})`));
    }
  }
}

console.log(`Analyzed ${files.length} source files (runtime import graph).`);
if (cyclic.length === 0) {
  console.log('✔ No circular dependencies found.');
  process.exit(0);
}


let strongCycles = [];
let lazyCycles = [];
for (const comp of cyclic) {
  const cycles = enumerateCycles(comp);
  for (const c of cycles) {
    if (c.severity === 'strong') strongCycles.push(c);
    else lazyCycles.push(c);
  }
}


if (strongCycles.length > 0) {
  console.error(`\n✖ Found ${strongCycles.length} STRONG circular dependency cycle(s) (static imports only):\n`);
  for (const c of strongCycles) {
    console.error(`  ${c.nodes.map(rel).join(' → ')}`);
  }
  console.error('');
}


if (lazyCycles.length > 0) {
  console.error(`\n⚠ Found ${lazyCycles.length} LAZY circular dependency cycle(s) (contain dynamic imports):\n`);
  
  const lazyEdgeSources = new Map(); 
  for (const c of lazyCycles) {
    
    for (let i = 0; i < c.nodes.length; i++) {
      const from = c.nodes[i];
      const to = c.nodes[(i + 1) % c.nodes.length];
      const edgeType = graph.get(from)?.get(to);
      if (edgeType === 'lazy') {
        const key = `${rel(from)} →(lazy)→ ${rel(to)}`;
        lazyEdgeSources.set(key, (lazyEdgeSources.get(key) || 0) + 1);
      }
    }
  }
  console.error('  Root-cause lazy edges (dynamic imports that close cycles):');
  for (const [edge, count] of lazyEdgeSources) {
    console.error(`    ${edge}  [closes ${count} cycle(s)]`);
  }
  console.error('');
  console.error('  Sample lazy cycles (showing first 5):');
  for (const c of lazyCycles.slice(0, 5)) {
    const annotated = c.nodes.map((n, i) => {
      const next = c.nodes[(i + 1) % c.nodes.length];
      const type = graph.get(n)?.get(next);
      return rel(n) + (type === 'lazy' ? ' →(lazy)→' : ' →');
    }).join(' ');
    console.error(`    ${annotated} [back to start]`);
  }
  if (lazyCycles.length > 5) {
    console.error(`    ... and ${lazyCycles.length - 5} more`);
  }
  console.error('');
}


const totalStrong = strongCycles.length;
const totalLazy = lazyCycles.length;
console.error(`Summary: ${totalStrong} strong cycle(s), ${totalLazy} lazy cycle(s)`);

if (totalStrong > 0) {
  console.error('Strong cycles are blocking — must be fixed before merge.');
  process.exit(1);
} else if (totalLazy > 0 && STRICT) {
  console.error('Strict mode: lazy cycles treated as blocking.');
  process.exit(1);
} else if (totalLazy > 0) {
  console.error('Lazy cycles are warnings — not blocking (use --strict to enforce).');
  process.exit(0);
} else {
  process.exit(0);
}
