"""
core/generator.py
Оркестрация многошаговой генерации контента.
Цепочка: идеи -> контент-план -> структура эпизода -> описание -> текст озвучки.
"""

from __future__ import annotations
import re
import json
from datetime import date

from services.llm_service import generate_json
from core import prompts


# Форматы с двумя говорящими (собеседник осмыслен).
DIALOG_FORMATS = {"интервью с гостем", "дискуссия двух ведущих"}


def _safe(value, default="не указано"):
    """Подстановка значения по умолчанию для пустых полей."""
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return value


def _norm(text) -> str:
    return (text or "").strip().lower()


# =====================================================================
#  ДЕТЕКТОРЫ ФОРМАТА / ТОНА / АУДИТОРИИ
# =====================================================================

def _is_fairytale_format(params: dict) -> bool:
    """Формат «сказка»: сюжетная структура-арка, единый рассказчик,
    поле собеседника игнорируется. Ортогонален тону."""
    return "сказк" in _norm(params.get("format"))


def _is_fairytale_tone(params: dict) -> bool:
    """Тон «сказочный»: лексика, ритм, обороты. Комбинируется с любым форматом."""
    tone = _norm(params.get("tone"))
    return "сказоч" in tone or "сказк" in tone


def _is_fairytale(params: dict) -> bool:
    """Совместимость со старым кодом: «сказочный опыт» включается, если выбран
    формат-сказка ИЛИ тон сказочный. Для нарративной механики используются
    отдельные детекторы _is_fairytale_format/_is_fairytale_tone."""
    return _is_fairytale_format(params) or _is_fairytale_tone(params)


# --- Маркеры детской аудитории (с учётом падежей и синонимов) ---
_CHILD_AUDIENCE_MARKERS = (
    "дет",          # дети, детей, детская, детсад, для детей
    "малыш",        # малыши, малышам
    "дошкол",       # дошкольники, дошкольного возраста
    "ребён", "ребен",   # ребёнок, ребенок
    "школьник",     # школьники, младшие школьники
    "младшего школьного", "младший школьный", "младшие школьник",
    "младшеклассник",
    "подрост",      # подростки, подростков, подростковая
    "тинейджер",
    "первоклассник", "второклассник","третьеклассник","пятиклассник","старшеклассник",
)

# «начальн…» засчитывается ТОЛЬКО в связке со школой (чтобы не путать
# с «начальник»).
_CHILD_SCHOOL_MARKERS = (
    "начальная школа", "начальной школ", "начальную школ",
    "начальных класс", "начальная ступень",
)

# Явные переопределения из аудитории/пожеланий (сильнее автодетекта).
_FORCE_CHILD_MARKERS = ("для детей", "детская аудитория", "детям", "для малышей")
_FORCE_ADULT_MARKERS = ("для взрослых", "взрослая аудитория", "18+",
                        "сказка для взрослых", "не для детей")


def _is_child_audience(params: dict) -> bool:
    """Определяет, детская ли аудитория.
    Приоритет: явные переопределения (взрослые > дети) -> школьные маркеры
    «начальн…» -> общие маркеры. Учитывает поле аудитории и доп. пожелания."""
    audience = _norm(params.get("audience"))
    wishes = _norm(params.get("extra_notes"))
    haystack = f"{audience} {wishes}"

    # Явные переопределения. Взрослые имеют приоритет над детьми.
    for m in _FORCE_ADULT_MARKERS:
        if m in haystack:
            return False
    for m in _FORCE_CHILD_MARKERS:
        if m in haystack:
            return True

    # «начальн…» — только со школой.
    if "начальн" in haystack:
        if any(s in haystack for s in _CHILD_SCHOOL_MARKERS):
            return True

    for m in _CHILD_AUDIENCE_MARKERS:
        if m in haystack:
            return True

    return False


def _is_dialog(params: dict) -> bool:
    """Диалоговый формат (два говорящих). Сказка НЕ диалоговая независимо
    от названия формата."""
    if _is_fairytale_format(params):
        return False
    return (params.get("format") or "").strip() in DIALOG_FORMATS


def _partner_name(params: dict) -> str:
    """Имя собеседника — только для диалоговых форматов.
    Для сольных форматов и сказки поле игнорируется полностью."""
    if not _is_dialog(params):
        return ""
    return (params.get("guest_name") or "").strip()


def _build_source_block(material_text: str) -> str:
    if material_text and material_text.strip():
        return prompts.SOURCE_MATERIAL_TEMPLATE.format(material_text=material_text)
    return ""


def _extra_notes_block(params: dict) -> str:
    notes = (params.get("extra_notes") or "").strip()
    if not notes:
        return ""
    return prompts.EXTRA_NOTES_TEMPLATE.format(extra_notes=notes)


def _partner_param_line(params: dict) -> str:
    """Строка параметра имени собеседника для шапки промптов (или пусто)."""
    if not _is_dialog(params):
        return ""
    name = _partner_name(params) or "не указано"
    return f"- Имя собеседника: {name}"


def _child_safety_block(params: dict) -> str:
    """Блок детской безопасности — только при детской аудитории.
    Для сказки — «сказочный» блок; для остальных форматов — нейтральный."""
    if not _is_child_audience(params):
        return ""
    if _is_fairytale_format(params):
        return prompts.CHILD_SAFETY_BLOCK
    return prompts.CHILD_SAFETY_GENERIC_BLOCK


def _fairytale_text_block(params: dict) -> str:
    """Собирает сказочный блок для текста озвучки: нарратив (формат) +
    стиль (формат-сказка всегда, либо тон сказочный) + детская безопасность."""
    parts = []
    if _is_fairytale_format(params):
        parts.append(prompts.FAIRYTALE_NARRATIVE_BLOCK)
    # Стиль: формат-сказка всегда тянет стиль; либо явно выбран сказочный тон.
    if _is_fairytale_format(params) or _is_fairytale_tone(params):
        parts.append(prompts.FAIRYTALE_STYLE_BLOCK)
    safety = _child_safety_block(params)
    if safety:
        parts.append(safety)
    return "\n".join(parts)


# =====================================================================
#  ЗАЩИТА ОТ СЛОВ СО СМЕШАННЫМ АЛФАВИТОМ
# =====================================================================

# Встроенный словарь по умолчанию. Пользовательский словарь из БД имеет
# ПРИОРИТЕТ и перекрывает эти значения (см. _merged_fix_map).
_MIXED_FIX_MAP = {
    "фотоchromия": "фотохромия",
    "фотоchromизм": "фотохромизм",
    "chromия": "хромия",
    "ferroэлектрик": "ферроэлектрик",
    "ferroэлектрический": "ферроэлектрический",
    "photoизомеризация": "фотоизомеризация",
    "isoмер": "изомер",
    "isoмеризация": "изомеризация",
}


def _merged_fix_map(user_map: dict | None) -> dict:
    """Объединяет встроенный и пользовательский словари.
    Пользовательские записи (из БД) перекрывают встроенные.
    Ключи приводятся к нижнему регистру для регистронезависимого поиска."""
    merged = {k.lower(): v for k, v in _MIXED_FIX_MAP.items()}
    if user_map:
        for k, v in user_map.items():
            if k and v:
                merged[k.strip().lower()] = v.strip()
    return merged


def _has_mixed_alphabet(word: str) -> bool:
    has_cyr = bool(re.search(r"[а-яё]", word, re.IGNORECASE))
    has_lat = bool(re.search(r"[a-z]", word, re.IGNORECASE))
    return has_cyr and has_lat


def _fix_mixed_language(text: str, fix_map: dict | None = None) -> str:
    """Исправляет смешанные слова по объединённому словарю.
    fix_map — уже слитый словарь (нижний регистр ключей); если None, берётся
    только встроенный."""
    if not text:
        return text
    if fix_map is None:
        fix_map = _merged_fix_map(None)

    def repl(match: "re.Match") -> str:
        word = match.group(0)
        if not _has_mixed_alphabet(word):
            return word
        low = word.lower()
        if low in fix_map:
            fixed = fix_map[low]
            if word[:1].isupper():
                fixed = fixed[:1].upper() + fixed[1:]
            return fixed
        return word

    return re.sub(r"[A-Za-zА-Яа-яЁё]+", repl, text)


def _collect_mixed_words(lines: list, user_map: dict | None = None) -> list:
    """Находит смешанные слова, которых НЕТ в объединённом словаре
    (ни встроенном, ни пользовательском) — их стоит занести в словарь."""
    fix_map = _merged_fix_map(user_map)
    found = []
    for line in lines:
        for w in re.findall(r"[A-Za-zА-Яа-яЁё]+", line.get("text", "")):
            if _has_mixed_alphabet(w) and w.lower() not in fix_map:
                found.append(w)
    return found


# --- Шаг 1: идеи выпусков ---
def generate_ideas(params: dict, *, n_ideas: int = 8, material_text: str = "") -> list[dict]:
    prompt = prompts.IDEAS_PROMPT.format(
        n_ideas=n_ideas,
        podcast_name=_safe(params.get("podcast_name")),
        topic=_safe(params.get("topic")),
        audience=_safe(params.get("audience")),
        format=_safe(params.get("format")),
        tone=_safe(params.get("tone")),
        duration=_safe(params.get("duration")),
        source_material_block=_build_source_block(material_text),
        extra_notes_block=_extra_notes_block(params),
    )
    result = generate_json(prompt, temperature=0.85)
    return result.get("ideas", [])


# --- Шаг 2: контент-план ---
def generate_content_plan(params: dict, ideas: list[dict], *, horizon: int = 8) -> list[dict]:
    start = params.get("start_date") or date.today().isoformat()
    prompt = prompts.CONTENT_PLAN_PROMPT.format(
        horizon=horizon,
        podcast_name=_safe(params.get("podcast_name")),
        topic=_safe(params.get("topic")),
        audience=_safe(params.get("audience")),
        frequency=_safe(params.get("frequency")),
        start_date=start,
        ideas_json=json.dumps(ideas, ensure_ascii=False, indent=2),
        extra_notes_block=_extra_notes_block(params),
    )
    result = generate_json(prompt, temperature=0.4)
    return result.get("content_plan", [])


# --- Шаг 3: структура эпизода ---
def generate_episode_structure(params: dict, episode: dict,
                               *, material_text: str = "") -> dict:
    """Для формата «сказка» строится сюжетная арка (FAIRYTALE_STRUCTURE_PROMPT),
    для остальных форматов — обычная блочная структура подкаста.
    material_text в структуру не прокидывается (как и раньше для всех форматов);
    источник участвует на этапах идей и текста озвучки."""
    if _is_fairytale_format(params):
        prompt = prompts.FAIRYTALE_STRUCTURE_PROMPT.format(
            topic=_safe(params.get("topic")),
            audience=_safe(params.get("audience")),
            tone=_safe(params.get("tone")),
            duration=_safe(params.get("duration")),
            episode_title=_safe(episode.get("title")),
            episode_summary=_safe(episode.get("topic_summary")),
            source_material_block=_build_source_block(material_text),
            extra_notes_block=_extra_notes_block(params),
            child_safety_block=_child_safety_block(params),
        )
        return generate_json(prompt, temperature=0.7)

    prompt = prompts.EPISODE_STRUCTURE_PROMPT.format(
        podcast_name=_safe(params.get("podcast_name")),
        host_name=_safe(params.get("host_name")),
        topic=_safe(params.get("topic")),
        audience=_safe(params.get("audience")),
        format=_safe(params.get("format")),
        tone=_safe(params.get("tone")),
        duration=_safe(params.get("duration")),
        episode_title=_safe(episode.get("title")),
        episode_summary=_safe(episode.get("topic_summary")),
        extra_notes_block=_extra_notes_block(params),
    )
    return generate_json(prompt, temperature=0.6)


# --- Шаг 4: описание выпуска ---
def generate_description(params: dict, episode: dict, structure: dict) -> dict:
    prompt = prompts.DESCRIPTION_PROMPT.format(
        podcast_name=_safe(params.get("podcast_name")),
        topic=_safe(params.get("topic")),
        audience=_safe(params.get("audience")),
        tone=_safe(params.get("tone")),
        episode_title=_safe(episode.get("title")),
        episode_summary=_safe(episode.get("topic_summary")),
        structure_json=json.dumps(structure, ensure_ascii=False),
        extra_notes_block=_extra_notes_block(params),
    )
    return generate_json(prompt, temperature=0.7)


# --- Конспект статьи ---
def summarize_article(article_text: str, *, article_type: str = "популярная") -> dict:
    prompt = prompts.ARTICLE_SUMMARY_PROMPT.format(
        article_type=article_type,
        article_text=article_text,
    )
    return generate_json(prompt, temperature=0.2)


# =====================================================================
#  ШАГ 5: ТЕКСТ ДЛЯ ОЗВУЧКИ (TTS)
# =====================================================================

def _summarize_done_lines(done_lines: list, *, max_chars: int = 1500) -> str:
    chunks = []
    for ln in done_lines:
        sp = (ln.get("speaker") or "").strip()
        if sp == "__block__":
            chunks.append(f"[Блок: {ln.get('text', '')}]")
            continue
        txt = (ln.get("text") or "").strip()
        if not txt:
            continue
        snippet = txt if len(txt) <= 160 else txt[:160].rstrip() + "…"
        prefix = f"{sp}: " if sp else ""
        chunks.append(prefix + snippet)
    summary = "\n".join(chunks)
    if len(summary) > max_chars:
        summary = "…\n" + summary[-max_chars:]
    return summary


def _build_prev_context_block(params: dict, done_lines: list) -> str:
    """Контекст уже сгенерированных блоков. Для сказки — единая история
    (без правил чередования реплик), для остального — диалоговый контекст."""
    if not done_lines:
        return ""
    summary = _summarize_done_lines(done_lines)
    if not summary.strip():
        return ""
    if _is_fairytale_format(params):
        return prompts.PREV_CONTEXT_FAIRYTALE_TEMPLATE.format(prev_summary=summary)
    return prompts.PREV_CONTEXT_TEMPLATE.format(prev_summary=summary)


def _build_speakers_rule(params: dict) -> str:
    """Правило говорящих в зависимости от формата."""
    if _is_fairytale_format(params):
        return prompts.SPEAKERS_RULE_FAIRYTALE

    fmt = (params.get("format") or "").strip()
    host = _safe(params.get("host_name"), "Ведущий")
    partner = _partner_name(params) or "Гость"
    if fmt == "интервью с гостем":
        return prompts.SPEAKERS_RULE_INTERVIEW.format(
            host_name=host, partner_name=partner)
    if fmt == "дискуссия двух ведущих":
        host_label = (params.get("host_name") or "").strip() or "Ведущий 1"
        partner_label = _partner_name(params) or "Ведущий 2"
        return prompts.SPEAKERS_RULE_DISCUSSION.format(
            host_label=host_label, partner_label=partner_label)
    return prompts.SPEAKERS_RULE_SOLO.format(host_name=host)


def _build_position_block(params: dict, episode: dict,
                          is_first: bool, is_last: bool) -> str:
    """Указания по позиции блока: интро / середина / финал.
    Для формата-сказки — позиции сюжетной арки (зачин / развитие / развязка)."""
    # Формат-сказка: используем сказочные позиционные шаблоны.
    if _is_fairytale_format(params):
        if is_first:
            return prompts.POSITION_FAIRYTALE_FIRST
        if is_last:
            return prompts.POSITION_FAIRYTALE_LAST
        return prompts.POSITION_FAIRYTALE_MIDDLE

    dialog = _is_dialog(params)

    if is_last:
        thanks_rule = (prompts.THANKS_RULE_DIALOG if dialog
                       else prompts.THANKS_RULE_SOLO)
        return prompts.POSITION_LAST_TEMPLATE.format(thanks_rule=thanks_rule)

    if not is_first:
        return prompts.POSITION_MIDDLE_TEMPLATE

    # --- Это интро. ---
    podcast_name = (params.get("podcast_name") or "").strip()
    partner = _partner_name(params)

    if podcast_name:
        greeting_rule = ("- Поздоровайся со слушателями и кратко обозначь "
                         f"подкаст (например, «Привет! Это подкаст “{podcast_name}”»).")
    else:
        greeting_rule = ("- Поздоровайся со слушателями коротко и дружелюбно "
                         "(без названия подкаста, оно не задано).")

    if dialog and partner and partner.lower() not in ("гость", "не указано"):
        guest_intro_rule = ("- Представь собеседника по имени (используй "
                            "имя/должность из дополнительных пожеланий, если они "
                            f"заданы): {partner}. Это единственное место, где "
                            "собеседник представляется. Не выдумывай отчество, "
                            "фамилию или должность, которых нет ни в этом имени, "
                            "ни в пожеланиях.")
    elif dialog:
        guest_intro_rule = ("- Кратко представь собеседника/эксперта "
                            "(конкретное имя не задано — обозначь его роль).")
    else:
        guest_intro_rule = ("- Формат СОЛЬНЫЙ: собеседника НЕТ, представлять "
                            "некого. НЕ упоминай гостя и НЕ обращайся к второму "
                            "лицу — только к слушателям.")

    ep_num = episode.get("episode_number")
    if ep_num == 1:
        first_episode_rule = ("- Это, по нумерации, ПЕРВЫЙ выпуск цикла: НЕ "
                              "ссылайся на прошлые выпуски, не намекай, что тема "
                              "уже поднималась. (Если в дополнительных пожеланиях "
                              "указано иное — следуй пожеланиям.)")
    else:
        first_episode_rule = ("- Это не первый выпуск цикла: уместна короткая "
                              "отсылка к подкасту в целом, но без пересказа "
                              "прошлых эпизодов. (Если в дополнительных "
                              "пожеланиях указано иное — следуй пожеланиям.)")

    return prompts.POSITION_FIRST_TEMPLATE.format(
        greeting_rule=greeting_rule,
        guest_intro_rule=guest_intro_rule,
        first_episode_rule=first_episode_rule,
    )


def generate_spoken_block(params: dict, episode: dict, block: dict,
                          *, material_text: str = "", done_lines: list | None = None,
                          block_index: int = 1, block_total: int = 1,
                          user_map: dict | None = None) -> list:
    """Генерирует реплики для одного блока структуры.
    user_map — пользовательский словарь замен смешанных слов (из БД)."""
    is_first = block_index <= 1
    is_last = block_index >= block_total
    is_solo = not _is_dialog(params)
    fix_map = _merged_fix_map(user_map)

    prompt = prompts.SPOKEN_TEXT_PROMPT.format(
        podcast_name=_safe(params.get("podcast_name"), ""),
        topic=_safe(params.get("topic")),
        audience=_safe(params.get("audience")),
        format=_safe(params.get("format")),
        tone=_safe(params.get("tone")),
        host_name=_safe(params.get("host_name"), "Ведущий"),
        partner_param_line=_partner_param_line(params),
        episode_title=episode.get("title", ""),
        episode_summary=episode.get("topic_summary", ""),
        block_index=block_index,
        block_total=block_total,
        block_name=block.get("name", ""),
        block_duration=block.get("duration", ""),
        block_purpose=block.get("purpose", ""),
        block_points="; ".join(block.get("talking_points", [])),
        position_block=_build_position_block(params, episode, is_first, is_last),
        source_material_block=_build_source_block(material_text),
        prev_context_block=_build_prev_context_block(params, done_lines or []),
        extra_notes_block=_extra_notes_block(params),
        speakers_rule=_build_speakers_rule(params),
        solo_schema_note=(prompts.SOLO_SCHEMA_NOTE if is_solo else ""),
        fairytale_block=_fairytale_text_block(params),
    )
    data = generate_json(prompt, temperature=0.8)
    lines = data.get("lines", [])
    for ln in lines:
        ln["text"] = _fix_mixed_language(ln.get("text", ""), fix_map)
        # Подстраховка: в сольном формате и сказке принудительно очищаем speaker.
        if is_solo:
            ln["speaker"] = ""
    return lines


def generate_full_spoken_text(params: dict, episode: dict, structure: dict,
                              *, material_text: str = "",
                              user_map: dict | None = None) -> list:
    all_lines = []
    blocks = structure.get("blocks", [])
    total = len(blocks)
    for i, block in enumerate(blocks, start=1):
        all_lines.append({"speaker": "__block__", "text": block.get("name", "")})
        all_lines.extend(generate_spoken_block(
            params, episode, block, material_text=material_text,
            done_lines=all_lines, block_index=i, block_total=total,
            user_map=user_map))
    return all_lines


def review_full_spoken_text(params: dict, lines: list,
                            *, user_map: dict | None = None) -> list:
    """Финальная вычитка. Для сказки — редактор сказки (FAIRYTALE_REVIEW_PROMPT),
    для остальных форматов — редактор подкаста (SPOKEN_TEXT_REVIEW_PROMPT).
    Оба работают с массивом реплик (JSON in/out)."""
    if not lines:
        return lines
    fix_map = _merged_fix_map(user_map)
    is_solo = not _is_dialog(params)

    if _is_fairytale_format(params):
        child_review = (prompts.CHILD_SAFETY_REVIEW_LINE
                        if _is_child_audience(params) else "")
        prompt = prompts.FAIRYTALE_REVIEW_PROMPT.format(
            audience=_safe(params.get("audience")),
            child_safety_review=child_review,
            lines_json=json.dumps(lines, ensure_ascii=False, indent=2),
        )
    else:
        prompt = prompts.SPOKEN_TEXT_REVIEW_PROMPT.format(
            format=_safe(params.get("format")),
            host_name=_safe(params.get("host_name"), "Ведущий"),
            partner_name=_partner_name(params) or "собеседник",
            partner_param_line=_partner_param_line(params),
            lines_json=json.dumps(lines, ensure_ascii=False, indent=2),
        )

    try:
        data = generate_json(prompt, temperature=0.3)
        reviewed = data.get("lines")
        if not reviewed:
            return lines
        for ln in reviewed:
            ln["text"] = _fix_mixed_language(ln.get("text", ""), fix_map)
            if is_solo and ln.get("speaker") != "__block__":
                ln["speaker"] = ""
        return reviewed
    except Exception:
        return lines


def generate_tts_recommendation(params: dict) -> dict:
    is_dialog = _is_dialog(params)
    voices_rule = (prompts.VOICES_RULE_DIALOG if is_dialog
                   else prompts.VOICES_RULE_SOLO)

    # Сказочный голос: выбираем детский или взрослый вариант по аудитории.
    fairytale_rule = ""
    if _is_fairytale_format(params):
        fairytale_rule = (prompts.VOICES_RULE_FAIRYTALE_CHILD
                          if _is_child_audience(params)
                          else prompts.VOICES_RULE_FAIRYTALE_ADULT)

    prompt = prompts.TTS_VOICE_PROMPT.format(
        topic=_safe(params.get("topic")),
        audience=_safe(params.get("audience")),
        format=_safe(params.get("format")),
        tone=_safe(params.get("tone")),
        host_name=_safe(params.get("host_name"), "Ведущий"),
        partner_param_line=_partner_param_line(params),
        extra_notes_block=_extra_notes_block(params),
        voices_count_rule=voices_rule,
        fairytale_voice_rule=fairytale_rule,
    )
    result = generate_json(prompt, temperature=0.4)
    if not is_dialog and isinstance(result.get("voices"), list):
        result["voices"] = result["voices"][:1]
    return result


# --- Полный конвейер (для тестов) ---
def run_full_pipeline(params, *, n_ideas=8, horizon=8, material_text="", detail_first_n=0):
    ideas = generate_ideas(params, n_ideas=n_ideas, material_text=material_text)
    plan = generate_content_plan(params, ideas, horizon=horizon)
    episodes_detail = []
    for episode in plan[:detail_first_n]:
        structure = generate_episode_structure(params, episode)
        description = generate_description(params, episode, structure)
        episodes_detail.append(
            {"episode": episode, "structure": structure, "description": description})
    return {"ideas": ideas, "content_plan": plan, "episodes_detail": episodes_detail}
