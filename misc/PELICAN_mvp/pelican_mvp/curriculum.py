"""The reviewed knowledge trees and task plans for PELICAN curriculums."""

from __future__ import annotations

from dataclasses import dataclass, field
from .models import DiagnosticQuestion, KnowledgeNode, TutoringStrategy

@dataclass
class Curriculum:
    name: str
    nodes: dict[str, KnowledgeNode]
    diagnostics: dict[str, DiagnosticQuestion]
    task_steps: tuple[dict[str, str], ...]
    answer_aliases: dict[str, set[str]]
    tutor_hints: dict[TutoringStrategy, str]
    completion_message: str

    def successors(self, node_id: str) -> tuple[str, ...]:
        return tuple(node.node_id for node in self.nodes.values() if node_id in node.prerequisites)

    def first_task_step(self) -> dict[str, str]:
        return self.task_steps[0]

    def next_task_step(self, step_id: str) -> dict[str, str] | None:
        for index, step in enumerate(self.task_steps):
            if step["step_id"] == step_id:
                return self.task_steps[index + 1] if index + 1 < len(self.task_steps) else None
        raise ValueError(f"Unknown task step: {step_id}")

# --- CNN Curriculum ---

cnn_nodes = {
    "nn_basics": KnowledgeNode("nn_basics", "神經網路基礎", priority=99),
    "cnn_conv": KnowledgeNode(
        "cnn_conv", "卷積運算尺寸", prerequisites=("nn_basics",), priority=1
    ),
    "cnn_relu": KnowledgeNode(
        "cnn_relu", "ReLU 激活函數", prerequisites=("nn_basics",), priority=2
    ),
    "cnn_pool": KnowledgeNode(
        "cnn_pool", "池化層運算", prerequisites=("nn_basics",), priority=3
    ),
}

cnn_diagnostics = {
    "cnn_conv": DiagnosticQuestion(
        "cnn_conv",
        "診斷題：輸入圖片為 10x10，使用 3x3 卷積核、步幅 1、無填充，輸出的特徵圖長寬各是多少？",
        "8",
    ),
    "cnn_relu": DiagnosticQuestion(
        "cnn_relu",
        "診斷題：將尺寸為 5x5 的矩陣通過 ReLU 激活函數，輸出的矩陣尺寸是否會改變？(填：會/不會)",
        "不會",
    ),
    "cnn_pool": DiagnosticQuestion(
        "cnn_pool",
        "診斷題：特徵圖尺寸為 10x10，使用 2x2 的最大池化、步幅 2，輸出的特徵圖長寬各是多少？",
        "5",
    ),
}

cnn_task_steps = (
    {
        "step_id": "solve_conv",
        "node_id": "cnn_conv",
        "label": "求卷積層尺寸",
        "prompt": "原題第一步：輸入 28x28 灰階影像，卷積核 3x3、步幅 1、無填充。請計算輸出尺寸。",
        "expected": "26",
    },
    {
        "step_id": "solve_relu",
        "node_id": "cnn_relu",
        "label": "求 ReLU 尺寸",
        "prompt": "原題第二步：將 26x26 的特徵圖通過 ReLU 函數，輸出尺寸會變成多少？",
        "expected": "26",
    },
    {
        "step_id": "solve_pool",
        "node_id": "cnn_pool",
        "label": "求池化層尺寸",
        "prompt": "原題最後一步：對 26x26 的特徵圖使用 2x2、步幅 2 的最大池化。最終輸出尺寸是多少？",
        "expected": "13",
    },
)

cnn_aliases = {
    "26": {"26", "26x26", "26*26"},
    "13": {"13", "13x13", "13*13"},
    "8": {"8", "8x8", "8*8"},
    "5": {"5", "5x5", "5*5"},
    "不會": {"不會", "不變", "否", "不會改變"},
}

cnn_tutor_hints = {
    TutoringStrategy.CORRECTION: "你的答案還沒有符合「{label}」的條件。先回到題目的限制：{prompt}",
    TutoringStrategy.DECOMPOSITION: "我們先將問題拆解。請先確認你所列出的參數（如卷積核尺寸、步幅等）是否皆正確？",
    TutoringStrategy.SIMPLIFICATION: "先用較小的例子練習：{1, 2, 3} 和 {2, 3, 4} 的交集是什麼？再把同一個方法用回原題。",
    TutoringStrategy.EXPLANATION: "目前要處理的是「{label}」。先不要急著求最後答案，請看這個條件：{prompt}",
    TutoringStrategy.CONFIRMATION: "這一步正確。接下來請把這個結果帶入下一個條件。",
}

cnn_curriculum = Curriculum(
    name="CNN 卷積神經網路",
    nodes=cnn_nodes,
    diagnostics=cnn_diagnostics,
    task_steps=cnn_task_steps,
    answer_aliases=cnn_aliases,
    tutor_hints=cnn_tutor_hints,
    completion_message="答對了：最終輸出尺寸 = 13。原題完成。"
)

# --- Chinese History Curriculum ---

ch_nodes = {
    "hist_basics": KnowledgeNode("hist_basics", "歷史基礎觀念", priority=99),
    "ming_founding": KnowledgeNode("ming_founding", "明朝建立與朱元璋", prerequisites=("hist_basics",), priority=10),
    "ming_economy": KnowledgeNode("ming_economy", "明朝經濟與海禁", prerequisites=("ming_founding",), priority=8),
    "ming_politics": KnowledgeNode("ming_politics", "明朝政治制度與內閣", prerequisites=("ming_founding",), priority=9),
    "ming_decline": KnowledgeNode("ming_decline", "明末衰退與流寇", prerequisites=("ming_economy", "ming_politics"), priority=5),
    "ming_fall": KnowledgeNode("ming_fall", "明朝滅亡與清軍入關", prerequisites=("ming_decline",), priority=1),
}

ch_diagnostics = {
    "ming_founding": DiagnosticQuestion("ming_founding", "診斷題：明朝的開國皇帝是誰？", "朱元璋"),
    "ming_economy": DiagnosticQuestion("ming_economy", "診斷題：明朝初期為了防範倭寇，實施了什麼政策限制對外貿易？", "海禁"),
    "ming_politics": DiagnosticQuestion("ming_politics", "診斷題：明太祖廢除丞相後，後來逐漸形成哪個機構來協助皇帝處理政務？", "內閣"),
    "ming_decline": DiagnosticQuestion("ming_decline", "診斷題：明末導致內部動盪的民變中，最著名的領袖是誰？（闖王）", "李自成"),
    "ming_fall": DiagnosticQuestion("ming_fall", "診斷題：哪一位明朝將領引清兵入關，最終導致清朝入主中原？", "吳三桂"),
}

ch_task_steps = (
    {
        "step_id": "solve_founding",
        "node_id": "ming_founding",
        "label": "確認明朝建立時間",
        "prompt": "歷史分析題第一步：請回答明朝建立的西元年份是哪一年？",
        "expected": "1368",
    },
    {
        "step_id": "solve_decline",
        "node_id": "ming_decline",
        "label": "分析明末內憂",
        "prompt": "歷史分析題第二步：明末除了外患之外，內部發生了大規模的農民起義。請回答推翻明朝首都北京的農民起義軍領袖是誰？",
        "expected": "李自成",
    },
    {
        "step_id": "solve_fall",
        "node_id": "ming_fall",
        "label": "分析明朝滅亡關鍵",
        "prompt": "歷史分析題最後一步：李自成攻破北京後，駐守山海關的明朝將領因為利益衝突，決定引清軍入關。請問這位將領是誰？",
        "expected": "吳三桂",
    },
)

ch_aliases = {
    "朱元璋": {"明太祖", "洪武帝", "朱元璋"},
    "海禁": {"海禁政策", "片板不許下海", "海禁"},
    "內閣": {"內閣制", "明朝內閣", "內閣"},
    "李自成": {"闖王", "闖王李自成", "李自成"},
    "吳三桂": {"平西王", "吳三桂"},
    "1368": {"1368年", "西元1368年", "1368"},
}

ch_tutor_hints = {
    TutoringStrategy.CORRECTION: "你的歷史推論不符合「{label}」的史實。請重新思考這段歷史：{prompt}",
    TutoringStrategy.DECOMPOSITION: "我們先將這段歷史背景拆解。請先釐清當時的時空背景與主要人物關係，這樣合理嗎？",
    TutoringStrategy.SIMPLIFICATION: "想一下類似的歷史事件，例如前朝滅亡的原因，再套用到這裡。請重新思考。",
    TutoringStrategy.EXPLANATION: "目前的重點是「{label}」。我們先別急著下定論，看看史實線索：{prompt}",
    TutoringStrategy.CONFIRMATION: "這點理解非常正確！請把這個史實基礎帶入下一個歷史分析中。",
}

ch_curriculum = Curriculum(
    name="中國歷史：明朝的興衰",
    nodes=ch_nodes,
    diagnostics=ch_diagnostics,
    task_steps=ch_task_steps,
    answer_aliases=ch_aliases,
    tutor_hints=ch_tutor_hints,
    completion_message="完全正確！明朝最終因為內憂外患，加上吳三桂引清軍入關而正式滅亡。原題完成。"
)

CURRICULUMS = {
    "cnn": cnn_curriculum,
    "chinese_history": ch_curriculum,
}
