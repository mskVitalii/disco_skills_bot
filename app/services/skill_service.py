import random
from dataclasses import dataclass
from enum import Enum


class Difficulty(Enum):
    TRIVIAL = 6
    EASY = 8
    MEDIUM = 10
    CHALLENGING = 12
    FORMIDABLE = 13
    LEGENDARY = 14
    HEROIC = 15
    GODLY = 16
    IMPOSSIBLE = 18

    @classmethod
    def from_int(cls, value: int) -> "Difficulty":
        best = cls.TRIVIAL
        for d in cls:
            if d.value <= value:
                best = d
        return best

    @property
    def label_ru(self) -> str:
        return {
            6: "Тривиальная",
            8: "Лёгкая",
            10: "Средняя",
            12: "Сложная",
            13: "Грозная",
            14: "Легендарная",
            15: "Героическая",
            16: "Божественная",
            18: "Невозможная",
        }[self.value]


@dataclass
class DiceRoll:
    die1: int
    die2: int
    skill_level: int
    difficulty: int

    @property
    def total(self) -> int:
        return self.die1 + self.die2 + self.skill_level

    @property
    def is_critical_success(self) -> bool:
        return self.die1 == 6 and self.die2 == 6

    @property
    def is_critical_failure(self) -> bool:
        return self.die1 == 1 and self.die2 == 1

    @property
    def is_success(self) -> bool:
        if self.is_critical_failure:
            return False
        if self.is_critical_success:
            return True
        return self.total >= self.difficulty

    @property
    def result_label(self) -> str:
        if self.is_critical_success:
            return "КРИТИЧЕСКИЙ УСПЕХ ⚅⚅"
        if self.is_critical_failure:
            return "КРИТИЧЕСКИЙ ПРОВАЛ ⚀⚀"
        return "УСПЕХ ✅" if self.is_success else "ПРОВАЛ ❌"

    def format_html(self) -> str:
        diff_label = Difficulty.from_int(self.difficulty).label_ru
        return (
            f"🎲 [{self.die1}+{self.die2}] + {self.skill_level} "
            f"= <b>{self.total}</b> vs {self.difficulty} ({diff_label}) "
            f"— <b>{self.result_label}</b>"
        )


def roll_check(skill_level: int, difficulty: int) -> DiceRoll:
    return DiceRoll(
        die1=random.randint(1, 6),
        die2=random.randint(1, 6),
        skill_level=skill_level,
        difficulty=difficulty,
    )
