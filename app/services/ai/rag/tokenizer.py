# -*- coding: utf-8 -*-
"""中文分词 + 运维领域自定义词典，供 FTS5 索引和查询共用。

两类术语分治：
- A. 纯中文复合术语：jieba 词典即可生效，防 `广播风暴`/`链路抖动` 被拆碎。
- B. 含连字符/空格的英文术语：jieba 词典 + FTS5 tokenchars 协同（单独任一都不够）。
"""
import jieba

JIEBA_CUSTOM_WORDS = [
    "广播风暴", "路由震荡", "链路抖动", "端口闪断", "端口抖动",
    "单通", "半双工", "双工不匹配", "MAC漂移", "ARP欺骗",
    "CPU过载", "内存泄漏", "进程崩溃", "内核恐慌",
    "生成树", "快速生成树", "端口安全", "风暴抑制", "链路聚合",
    "动态路由", "静态路由", "路由重分布", "BGP邻居", "OSPF邻居",
    "VLAN间路由", "三层交换", "二层环路",
    "巡检", "故障定位", "根因分析", "割接", "回滚", "降级",
    "灰度发布", "配置备份", "配置恢复", "版本升级", "版本回退",
    "紧急告警", "重要告警", "次要告警", "警告告警", "提示告警",
]

ENGLISH_COMPOUND_TERMS = [
    "Err-Disable", "err-disable", "link-flap", "bpduguard", "udld",
    "security-violation", "port-mode-change", "channel-misconfig",
    "show interfaces", "show running-config", "show version",
    "display cpu-usage", "display interface", "display logbuffer",
    "BPDU Guard", "BPDU Filter", "UDLD", "STP", "RSTP", "MSTP",
    "SNMP", "NetFlow", "sFlow", "IPSLA",
    "GigabitEthernet", "TenGigabitEthernet", "FastEthernet",
]

for _w in JIEBA_CUSTOM_WORDS + ENGLISH_COMPOUND_TERMS:
    jieba.add_word(_w)


def tokenize(text: str) -> str:
    """中文分词为空格分隔的 token 串，供 FTS5 索引和查询共用。"""
    return " ".join(w for w in jieba.cut(text) if w.strip())
