"""Released capabilities used by the guide and its AI answers."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Feature:
    key: str
    title: str
    summary: str
    details: str
    related: tuple[str, ...] = ()
    changes: tuple[str, ...] = ()
    suggest: bool = True


FEATURES = (
    Feature('camp', '营地门牌', '查看你的营地概况。', '登录后汇总进行中的任务、角色成长和近期行动入口。', ('quests', 'tasks', 'growth'), suggest=False),
    Feature('journey', '冒险地图', '浏览冒险阶段和建设方向。', '实际执行可以从主线和副本入口继续。', ('quests', 'tasks'), suggest=False),
    Feature('settings', '营地设置', '查看和调整营地设置。', '设置用于管理营地偏好，登录和个人身份在角色账号管理。', ('account',), suggest=False),
    Feature('quests', '主线任务', '管理长期目标和里程碑。', '把一个方向整理成主线，用里程碑记录可检验的进展。', ('tasks', 'startup'), ('阶段 1 增加主线、里程碑与关联副本。',)),
    Feature('tasks', '副本任务', '把目标拆成可行动的任务。', '查看任务详情、使用 AI 一键拆解、完成时按规则获得奖励。', ('quests', 'focus', 'growth', 'startup'), ('阶段 1 支持任务拆解、完成与奖励。',)),
    Feature('focus', '专注沙漏', '开始一段计时或倒计时。', '可关联任务，结束的专注可以在历练手记中查看。', ('tasks', 'journal'), ('阶段 1 支持关联副本和记录实际专注时长。',)),
    Feature('journal', '历练手记', '查看和记录真实的行动。', '既可以回看专注记录，也可以补记未使用计时器的一次行动。', ('focus', 'tasks'), ('阶段 1 支持专注记录以及手动补记。',)),
    Feature('growth', '成长与奖励', '查看经验、等级、金币与奖励。', '通过任务等行动积累成长，回看奖励变化。', ('tasks', 'camp')),
    Feature('library', '藏经阁', '整理常用链接和书架。', '给链接分类，搜索、打开或复制。成功复制会增加该链接的使用次数。', ('distractions',), ('藏经阁上线后支持书架、筛选与复制计数。',)),
    Feature('shining-memories', '闪光的回忆', '记录重要的人、使用的物品和愿望。', '精神导师和朋友搭子记录经历，武器工坊记录资产，心愿单管理愿望与价格。', ('spirit-stones',), ('新增朋友搭子、关系双图和幸运值。', '武器工坊支持权益到期，心愿单保留价格记录。')),
    Feature('distractions', '杂念', '先记下打断注意力的想法。', '快速捕捉、搜索和整理杂念，也可授权 AI 归类，或在事件分析中选作背景。', ('life-os', 'spirit-stones'), ('新增杂念 AI 归类和原文回看。',)),
    Feature('startup', '启动状态', '从当前压力和能量找到下一步。', '确认状态后查看四色任务建议，也可围绕真实任务讨论如何开始。', ('quests', 'tasks', 'spirit-stones'), ('新增状态坐标及任务适配建议。',)),
    Feature('life-os', '人生运行系统', '记录近况、生活节奏和恢复过程。', '支持近期对话、周计划、双五层视角、最低保障清单与环境吸引子。', ('distractions', 'spirit-stones'), ('近期对话支持最多 20 轮，双五层按最近轮次显示散点。', '每日时间线按用户时区显示下一锚点。')),
    Feature('spirit-stones', '灵石区', '管理模型连接与模块调用。', '配置和测试模型，查看调用情况及 Supabase 配置状态。', ('startup', 'life-os'), ('新增 Supabase 配置只读展示。',), False),
    Feature('spirit-root', '灵根', '从文字里发现天赋和反复出现的信号。', '提交一段 AI 新发现或想法，探查后可以查看天赋强度、出现次数、记录历史和原文证据。', ('spirit-stones',), ('首次上线灵力探查、天赋与信号。', '新增底层天赋图腾、心神修炼、职业演化路径和长期验证方向。')),
    Feature('account', '角色账号', '登录、注册和管理账户。', '个人数据按账号独立存储。', ('settings', 'data'), suggest=False),
    Feature('artifact-spirit', '器灵', '了解功能、回看使用情况并提出问题。', '功能详情、使用提醒与当前会话问答共用同一份功能清单。', ('spirit-stones',), ('首次上线器灵导览、使用统计和问答。',), False),
    Feature('data', '数据与恢复', '了解备份、导出和恢复。', '可以下载 JSON 和 CSV 数据包，并查看恢复说明。完整备份与恢复按项目文档操作。', ('account',), suggest=False),
)
BY_KEY = {item.key: item for item in FEATURES}


def href(key):
    return '/' if key == 'camp' else '/' + key


def entries():
    return [asdict(item) | {'href': href(item.key)} for item in FEATURES]
