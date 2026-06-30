"""
app.py
Веб-интерфейс системы планирования контента подкаста (Streamlit).
Запуск: streamlit run app.py
"""

import json
import re
import datetime
from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from core import generator
from services import source_service, auth_service, db_service, export_service

db_service.init_db()

st.set_page_config(page_title="Контент-планер подкастов",
                   page_icon="🎙️", layout="centered")

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 3rem; }
      h1, h2, h3 { line-height: 1.25; }
      .stButton button { width: 100%; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
#  ВСПОМОГАТЕЛЬНОЕ: безопасное имя файла
# =====================================================================
def _safe_filename(text: str, default: str = "проект") -> str:
    text = (text or "").strip() or default
    text = re.sub(r'[\\/:*?"<>|]+', "", text)
    text = re.sub(r"\s+", "_", text)
    return text[:60] or default


# =====================================================================
#  АУТЕНТИФИКАЦИЯ
# =====================================================================
st.session_state.setdefault("user", None)


def render_auth():
    st.title("🎙️ Контент-планер подкастов")
    if db_service.user_count() == 0:
        st.info("Это первый запуск. Создайте учётную запись, чтобы начать.")
    tab_login, tab_register = st.tabs(["Вход", "Регистрация"])
    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Логин")
            p = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти", type="primary"):
                try:
                    st.session_state.user = auth_service.login(u, p)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    with tab_register:
        st.caption("Совет: придумайте надёжный уникальный пароль "
                   "(браузер может предупреждать о простых паролях).")
        with st.form("register_form"):
            u = st.text_input("Придумайте логин")
            p = st.text_input("Придумайте пароль", type="password")
            p2 = st.text_input("Повторите пароль", type="password")
            if st.form_submit_button("Зарегистрироваться"):
                if p != p2:
                    st.error("Пароли не совпадают.")
                else:
                    try:
                        st.session_state.user = auth_service.register(u, p)
                        st.success("Учётная запись создана. Входим…")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))


if st.session_state.user is None:
    render_auth()
    st.stop()

USER_ID = st.session_state.user["id"]


# =====================================================================
#  СПИСКИ И ИНИЦИАЛИЗАЦИЯ
# =====================================================================
FORMAT_OPTIONS = ["соло-монолог", "интервью с гостем", "дискуссия двух ведущих",
                  "обзор/разбор", "сторителлинг", "вопрос-ответ"]
FREQ_OPTIONS = ["ежедневно", "2 раза в неделю", "еженедельно",
                "раз в две недели", "ежемесячно"]
TONE_OPTIONS = ["дружелюбный", "экспертный", "ироничный",
                "мотивирующий", "академичный", "сказочный"]
DURATION_OPTIONS = ["10–15 мин", "20–30 мин", "40–60 мин"]
NEW_PROJECT_LABEL = "➕ Новый проект"
DIALOG_FORMATS = {"интервью с гостем", "дискуссия двух ведущих"}

_PARAM_DEFAULTS = {
    "p_topic": "", "p_audience": "", "p_format": FORMAT_OPTIONS[0],
    "p_frequency": "еженедельно", "p_podcast_name": "", "p_host_name": "",
    "p_guest_name": "", "p_tone": TONE_OPTIONS[0], "p_duration": "20–30 мин",
    "p_horizon": 8, "p_n_ideas": 8, "p_extra_notes": "",
}
for k, v in _PARAM_DEFAULTS.items():
    st.session_state.setdefault(k, v)

for key in ("params", "ideas", "content_plan", "details", "material_text"):
    st.session_state.setdefault(key, None)
st.session_state.setdefault("current_project_id", None)
st.session_state.setdefault("current_project_title", "")
st.session_state.setdefault("selected_material_ids", [])
st.session_state.setdefault("selected_idea_indexes", [])
st.session_state.setdefault("delete_mode", False)
st.session_state.setdefault("confirm_delete_ids", None)
st.session_state.setdefault("last_loaded_label", None)
st.session_state.setdefault("article_summary", None)
st.session_state.setdefault("article_source_text", "")
st.session_state.setdefault("summary_material_text", None)
st.session_state.setdefault("focus_required_fields", False)
st.session_state.setdefault("spoken_text", None)
st.session_state.setdefault("tts_voices", None)
st.session_state.setdefault("last_gen_params", None)
st.session_state.setdefault("regen_ask", None)
st.session_state.setdefault("pending_job", None)   # отложенная генерация
st.session_state.setdefault("saved_snapshot", None)  # снимок сохранённого состояния


def has_unsaved_work() -> bool:
    if st.session_state.ideas or st.session_state.content_plan:
        return True
    for k, v in _PARAM_DEFAULTS.items():
        if st.session_state.get(k) != v:
            return True
    return False


def count_changed_params() -> int:
    advanced_keys = ["p_podcast_name", "p_host_name", "p_guest_name", "p_tone",
                     "p_duration", "p_horizon", "p_n_ideas", "p_extra_notes"]
    return sum(1 for k in advanced_keys
               if st.session_state.get(k) != _PARAM_DEFAULTS[k])


def collect_params() -> dict:
    return {
        "topic": st.session_state.p_topic,
        "audience": st.session_state.p_audience,
        "format": st.session_state.p_format,
        "frequency": st.session_state.p_frequency,
        "podcast_name": st.session_state.p_podcast_name,
        "host_name": st.session_state.p_host_name,
        "guest_name": st.session_state.p_guest_name,
        "tone": st.session_state.p_tone,
        "duration": st.session_state.p_duration,
        "extra_notes": st.session_state.p_extra_notes,
        "start_date": (st.session_state.get("_start_date").isoformat()
                       if st.session_state.get("_start_date") else None),
    }


def settings_changed() -> bool:
    snap = st.session_state.get("last_gen_params")
    if snap is None:
        return False
    return snap != collect_params()


def resolve_material() -> str:
    ids = st.session_state.get("selected_material_ids", [])
    chosen = db_service.get_materials_by_ids(USER_ID, ids)
    parts = [f"=== Источник: {m['name']} ===\n{m['content']}" for m in chosen]
    if st.session_state.get("summary_material_text"):
        parts.append(st.session_state.summary_material_text)
    return "\n\n".join(parts)[:20000]


# ---- Снимок состояния для определения «есть несохранённые изменения» ----
def build_project_data() -> dict:
    return {
        "params": st.session_state.params,
        "ideas": st.session_state.ideas,
        "content_plan": st.session_state.content_plan,
        "details": st.session_state.details,
        "spoken_text": st.session_state.spoken_text,
        "tts_voices": st.session_state.tts_voices,
        "summary_material_text": st.session_state.summary_material_text,
        "selected_material_ids": st.session_state.selected_material_ids,
        "selected_idea_indexes": st.session_state.selected_idea_indexes,
        "horizon": st.session_state.p_horizon,
        "n_ideas": st.session_state.p_n_ideas,
    }


def make_snapshot() -> str:
    """Стабильная строковая подпись состояния (для сравнения)."""
    return json.dumps(build_project_data(), ensure_ascii=False, sort_keys=True)


def has_changes_vs_snapshot() -> bool:
    snap = st.session_state.get("saved_snapshot")
    if snap is None:
        return True
    return snap != make_snapshot()


def reset_to_new_project():
    for k, v in _PARAM_DEFAULTS.items():
        st.session_state[k] = v
    for key in ("params", "ideas", "content_plan", "details", "material_text",
                "summary_material_text", "spoken_text", "tts_voices",
                "last_gen_params", "regen_ask", "pending_job", "saved_snapshot"):
        st.session_state[key] = None
    st.session_state.current_project_id = None
    st.session_state.current_project_title = ""
    st.session_state.selected_material_ids = []
    st.session_state.selected_idea_indexes = []
    st.session_state.last_loaded_label = None
    for m in db_service.list_materials(USER_ID):
        st.session_state.pop(f"mat_{m['id']}", None)


def load_project_into_state(proj: dict):
    d = proj["data"]
    p = d.get("params") or {}
    st.session_state.p_topic = p.get("topic", "")
    st.session_state.p_audience = p.get("audience", "")
    st.session_state.p_format = p.get("format", FORMAT_OPTIONS[0])
    st.session_state.p_frequency = p.get("frequency", "еженедельно")
    st.session_state.p_podcast_name = p.get("podcast_name", "")
    st.session_state.p_host_name = p.get("host_name", "")
    st.session_state.p_guest_name = p.get("guest_name", "")
    st.session_state.p_tone = p.get("tone", TONE_OPTIONS[0])
    st.session_state.p_duration = p.get("duration", "20–30 мин")
    st.session_state.p_horizon = d.get("horizon", 8)
    st.session_state.p_n_ideas = d.get("n_ideas", 8)
    st.session_state.p_extra_notes = p.get("extra_notes", "")
    st.session_state.params = d.get("params")
    st.session_state.ideas = d.get("ideas")
    st.session_state.content_plan = d.get("content_plan")
    st.session_state.details = d.get("details")
    st.session_state.spoken_text = d.get("spoken_text")
    st.session_state.tts_voices = d.get("tts_voices")
    st.session_state.summary_material_text = d.get("summary_material_text")
    st.session_state.selected_material_ids = d.get("selected_material_ids", [])
    st.session_state.selected_idea_indexes = d.get("selected_idea_indexes", [])
    st.session_state.last_gen_params = d.get("params")
    st.session_state.current_project_id = proj["id"]
    st.session_state.current_project_title = proj["title"]
    # Фиксируем снимок «чистого» загруженного состояния.
    st.session_state.saved_snapshot = make_snapshot()


# =====================================================================
#  ШАГИ КОНВЕЙЕРА
# =====================================================================
def _step_ideas(params, material):
    st.session_state.ideas = generator.generate_ideas(
        params, n_ideas=st.session_state.p_n_ideas, material_text=material)
    st.session_state.selected_idea_indexes = list(
        range(len(st.session_state.ideas)))


def _step_plan(params):
    chosen_idx = st.session_state.get("selected_idea_indexes", [])
    ideas_for_plan = ([st.session_state.ideas[i] for i in chosen_idx]
                      if chosen_idx else st.session_state.ideas)
    st.session_state.content_plan = generator.generate_content_plan(
        params, ideas_for_plan, horizon=st.session_state.p_horizon)


def _step_structure(params, episode):
    structure = generator.generate_episode_structure(params, episode)
    description = generator.generate_description(params, episode, structure)
    st.session_state.details = {"structure": structure,
                                "description": description,
                                "episode": episode}


def _step_spoken(params, material, status_box=None, do_review=True):
    """status_box — контейнер (st.empty), куда рисуется st.status под кнопкой.
    do_review — запускать ли финальный редакторский проход."""
    details = st.session_state.details
    episode = details.get("episode") or {}
    structure = details["structure"]
    blocks = structure.get("blocks", [])
    all_lines = []

    box = status_box if status_box is not None else st
    with box.status("🎤 Генерирую текст для озвучки…", expanded=True) as status:
        for bi, block in enumerate(blocks):
            status.update(
                label=f"Блок {bi + 1} из {len(blocks)}: "
                      f"{block.get('name', '—')}")
            all_lines.append({"speaker": "__block__",
                              "text": block.get("name", "")})
            all_lines.extend(generator.generate_spoken_block(
                params, episode, block, material_text=material,
                done_lines=all_lines,
                block_index=bi + 1, block_total=len(blocks)))
        if do_review:
            status.update(label="Финальная вычитка текста…")
            all_lines = generator.review_full_spoken_text(params, all_lines)
        status.update(label="Готовлю рекомендации по голосам…")
        st.session_state.spoken_text = all_lines
        st.session_state.tts_voices = generator.generate_tts_recommendation(params)
        status.update(label="Готово ✅", state="complete", expanded=False)



def request_chain(upto: str, *, from_step: str, episode=None):
    """Ставит задание на пересборку и перезапускает прогон.
    Тяжёлая работа выполнится в чистом прогоне (execute_pending_job),
    чтобы не было гонки виджетов с одновременными кликами."""
    st.session_state.pending_job = {
        "upto": upto, "from_step": from_step, "episode": episode}
    st.session_state.regen_ask = None
    st.rerun()


def execute_pending_job(spoken_status_box=None):
    """Выполняет отложенное задание генерации. Вызывается в начале прогона."""
    job = st.session_state.pending_job
    st.session_state.pending_job = None  # снимаем сразу, чтобы не зациклить

    order = ["ideas", "plan", "structure", "spoken"]
    params = collect_params()
    st.session_state.params = params
    material = resolve_material()
    st.session_state.material_text = material

    i_from = order.index(job["from_step"])
    i_upto = order.index(job["upto"])
    episode = job["episode"]

    # Если перегенерируется что-то выше озвучки — старый текст должен исчезнуть.
    if job["from_step"] in ("ideas", "plan", "structure"):
        st.session_state.spoken_text = None
        st.session_state.tts_voices = None

    try:
        for step in order[i_from:i_upto + 1]:
            if step == "ideas":
                with st.spinner("Генерирую идеи…"):
                    _step_ideas(params, material)
            elif step == "plan":
                with st.spinner("Строю контент-план…"):
                    _step_plan(params)
            elif step == "structure":
                with st.spinner("Проектирую структуру и описание…"):
                    _step_structure(params, episode)
            elif step == "spoken":
                _step_spoken(params, material, status_box=spoken_status_box,
                             do_review=st.session_state.get("spoken_do_review", True))
        st.session_state.last_gen_params = params
    except Exception as e:
        st.error(f"Ошибка генерации: {e}")


def run_generate_ideas():
    if not st.session_state.p_topic or not st.session_state.p_audience:
        st.error("Заполните обязательные поля: тематика и целевая аудитория.")
        return
    st.session_state.content_plan = None
    st.session_state.details = None
    st.session_state.spoken_text = None
    st.session_state.tts_voices = None
    st.session_state.focus_required_fields = False
    request_chain("ideas", from_step="ideas")


def render_regen_dialog(target, episode):
    """Рисует варианты пересборки прямо под кнопкой шага."""
    labels = {
        "plan": [("plan", "Только план (по текущим идеям)"),
                 ("ideas", "Идеи и план заново")],
        "structure": [("structure", "Только структуру"),
                      ("plan", "План и структуру"),
                      ("ideas", "Идеи, план и структуру")],
        "spoken": [("spoken", "Только текст"),
                   ("structure", "Структуру и текст"),
                   ("plan", "План, структуру и текст"),
                   ("ideas", "Идеи, план, структуру и текст")],
    }
    with st.container(border=True):
        st.warning("⚙️ Настройки слева изменились. Что обновить?")
        choice = st.radio("Вариант пересборки",
                          [lbl for _, lbl in labels[target]],
                          key=f"regen_choice_{target}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Выполнить", type="primary", key=f"regen_go_{target}"):
                from_step = next(fs for fs, lbl in labels[target] if lbl == choice)
                request_chain(target, from_step=from_step, episode=episode)
        with c2:
            if st.button("Отмена", key=f"regen_cancel_{target}"):
                st.session_state.regen_ask = None
                st.rerun()


# =====================================================================
#  ВЫПОЛНЕНИЕ ОТЛОЖЕННОГО ЗАДАНИЯ
#  Для шага "spoken" индикатор рисуется под кнопкой озвучки (см. шаг 4),
#  поэтому если задание — только spoken, отложим его исполнение до места
#  кнопки. Остальные задания выполняем здесь.
# =====================================================================
_pending = st.session_state.get("pending_job")
_run_spoken_inline = bool(_pending and _pending.get("upto") == "spoken"
                          and _pending.get("from_step") == "spoken")
if _pending and not _run_spoken_inline:
    execute_pending_job()


# =====================================================================
#  БОКОВАЯ ПАНЕЛЬ
# =====================================================================
with st.sidebar:
    st.markdown("## 🎙️ Контент-планер подкастов")
    st.success(f"Вы вошли как: {st.session_state.user['username']}")
    if st.button("Выйти"):
        st.session_state.user = None
        st.rerun()

    # --- Мои проекты ---
    st.divider()
    st.markdown("### 🗂️ Мои проекты")
    projects = db_service.list_projects(USER_ID)
    options = {f"{p['title']} (обн. {p['updated_at'][:10]})": p["id"]
               for p in projects}
    proj_list = [NEW_PROJECT_LABEL] + list(options.keys())
    chosen_proj = st.selectbox(
        "Проект", proj_list, key="project_selector",
        help="При переключении проекта несохранённые изменения текущего "
             "проекта будут потеряны. Сначала нажмите «Сохранить изменения» "
             "или «Сохранить как новый проект».")

    if chosen_proj == NEW_PROJECT_LABEL:
        if chosen_proj != st.session_state.get("last_loaded_label"):
            if has_unsaved_work():
                st.warning("⚠️ В текущем проекте есть несохранённые данные — "
                           "при создании нового они будут потеряны.")
                if st.button("Начать новый проект"):
                    reset_to_new_project()
                    st.session_state.last_loaded_label = NEW_PROJECT_LABEL
                    st.rerun()
            else:
                st.session_state.last_loaded_label = NEW_PROJECT_LABEL
    else:
        if chosen_proj != st.session_state.get("last_loaded_label"):
            # Предупреждаем, только если действительно есть что терять.
            if (st.session_state.get("current_project_id")
                    and has_changes_vs_snapshot()):
                st.warning("⚠️ В текущем проекте есть несохранённые изменения. "
                           "Загрузка другого проекта их сотрёт.")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("Загрузить всё равно", key="load_anyway"):
                        proj = db_service.get_project(USER_ID, options[chosen_proj])
                        load_project_into_state(proj)
                        st.session_state.last_loaded_label = chosen_proj
                        st.rerun()
                with cc2:
                    if st.button("Отмена", key="load_cancel"):
                        # Возврат на текущий проект в селекторе при следующем прогоне.
                        st.session_state.project_selector = (
                            st.session_state.get("last_loaded_label")
                            or NEW_PROJECT_LABEL)
                        st.rerun()
            else:
                proj = db_service.get_project(USER_ID, options[chosen_proj])
                load_project_into_state(proj)
                st.session_state.last_loaded_label = chosen_proj
                st.success("Проект загружён.")
                st.rerun()

    # --- Параметры подкаста ---
    st.divider()
    st.markdown("### ⚙️ Параметры подкаста")
    st.text_input("Тематика *", key="p_topic",
                  placeholder="напр. инвестиции для новичков")
    st.text_input("Целевая аудитория *", key="p_audience",
                  placeholder="напр. студенты 18–25")
    st.selectbox("Формат выпусков *", FORMAT_OPTIONS, key="p_format")
    st.selectbox("Частота публикаций *", FREQ_OPTIONS, key="p_frequency")

    changed = count_changed_params()
    adv_title = "Дополнительные параметры"
    if changed:
        adv_title += f" (изменено: {changed})"
    with st.expander(adv_title, expanded=bool(changed)):
        st.text_input("Название подкаста", key="p_podcast_name")
        st.text_input("Имя ведущего(-их)", key="p_host_name")
        st.text_input("Имя собеседника", key="p_guest_name",
            help="Имя второго участника: гостя в интервью или второго ведущего "
                 "в дискуссии. Для сольных форматов (соло-монолог, обзор, "
                 "сторителлинг, вопрос-ответ) это поле игнорируется.",
            placeholder="гость / второй ведущий; для соло не используется")
        st.selectbox("Тон и стиль", TONE_OPTIONS, key="p_tone")
        st.selectbox("Длительность выпуска", DURATION_OPTIONS, key="p_duration")
        st.slider("Сколько выпусков в плане", 4, 16, key="p_horizon")
        st.slider("Сколько идей сгенерировать", 4, 16, key="p_n_ideas")
        st.session_state["_start_date"] = st.date_input("Дата старта")
        st.text_area("Дополнительные пожелания", key="p_extra_notes",
            placeholder="что включить / чего избегать; например: «это первый "
                        "выпуск цикла» или «это НЕ первый выпуск, не здоровайся "
                        "как впервые»; как представить гостя; cold open и т.п.")

    if st.button("💡 Сгенерировать идеи", key="gen_ideas_sidebar", type="primary"):
        run_generate_ideas()

    # --- Материал-источник ---
    n_selected = len(st.session_state.get("selected_material_ids", []))
    src_title = "Материал-источник (необязательно)"
    if n_selected:
        src_title = f"Материал-источник (выбрано: {n_selected})"
    with st.expander(src_title, expanded=bool(n_selected)):
        st.caption("Загрузите новый источник или выберите из сохранённых.")
        st.markdown("**Добавить новый источник**")
        new_mode = st.radio("Тип", ["нет", "файл", "ссылка на статью"],
                            index=0, key="new_source_mode")
        if new_mode == "файл":
            up = st.file_uploader("Файл", type=source_service.SUPPORTED_FILE_TYPES,
                                  help="txt, md, pdf, docx, pptx, xlsx",
                                  key="new_file")
            if st.button("Сохранить файл в библиотеку", key="save_file_btn"):
                if up is None:
                    st.warning("Сначала выберите файл.")
                else:
                    try:
                        with st.spinner("Распознаю файл…"):
                            text = source_service.extract_text(
                                filename=up.name, file_bytes=up.getvalue())
                        db_service.add_material(USER_ID, "file", up.name, text)
                        st.success(f"Сохранено: {up.name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
        elif new_mode == "ссылка на статью":
            url_in = st.text_input("URL статьи", key="new_url")
            if st.button("Сохранить ссылку в библиотеку", key="save_url_btn"):
                if not url_in:
                    st.warning("Сначала введите URL.")
                else:
                    try:
                        with st.spinner("Загружаю статью…"):
                            text = source_service.extract_text(url=url_in)
                        db_service.add_material(USER_ID, "url", url_in, text)
                        st.success("Ссылка сохранена.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

        st.markdown("**Мои источники**")
        materials = db_service.list_materials(USER_ID)
        selected_ids = []
        if not materials:
            st.caption("Пока нет сохранённых источников.")
        else:
            for m in materials:
                icon = "📄" if m["source_type"] == "file" else "🔗"
                checked_default = m["id"] in st.session_state.selected_material_ids
                if st.checkbox(f"{icon} {m['name']}", value=checked_default,
                               key=f"mat_{m['id']}"):
                    selected_ids.append(m["id"])
            st.session_state.selected_material_ids = selected_ids

            st.markdown("---")
            if not st.session_state.delete_mode:
                if st.button("🗑 Удалить источники…"):
                    st.session_state.delete_mode = True
                    st.session_state.confirm_delete_ids = None
                    st.rerun()
            else:
                st.caption("Отметьте источники для удаления:")
                del_ids = []
                for m in materials:
                    icon = "📄" if m["source_type"] == "file" else "🔗"
                    if st.checkbox(f"удалить {icon} {m['name']}",
                                   key=f"delpick_{m['id']}"):
                        del_ids.append(m["id"])
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Продолжить"):
                        if del_ids:
                            st.session_state.confirm_delete_ids = del_ids
                        else:
                            st.warning("Ничего не отмечено.")
                with c2:
                    if st.button("Закрыть"):
                        st.session_state.delete_mode = False
                        st.session_state.confirm_delete_ids = None
                        st.rerun()

    # --- Дополнительные инструменты ---
    st.divider()
    st.markdown("### 🧰 Дополнительные инструменты")
    with st.expander("Сделать конспект статьи"):
        st.caption("Подайте статью — получите строгий конспект справа.")
        art_type = st.radio("Тип статьи", ["популярная", "научная"],
                            horizontal=True, key="art_type")
        art_source = st.radio("Источник статьи",
                              ["загрузить файл", "ссылка", "из библиотеки"],
                              key="art_source")
        save_to_lib = st.checkbox("Добавить источник в библиотеку", value=False,
                                  key="art_save_lib")

        art_text_source = None
        if art_source == "загрузить файл":
            af = st.file_uploader("Файл статьи",
                                  type=source_service.SUPPORTED_FILE_TYPES,
                                  key="art_file")
            if af is not None:
                art_text_source = ("file", af)
        elif art_source == "ссылка":
            au = st.text_input("URL статьи", key="art_url")
            if au:
                art_text_source = ("url", au)
        else:
            mats = db_service.list_materials(USER_ID)
            if mats:
                labels = {m["name"]: m["id"] for m in mats}
                pick = st.selectbox("Выберите источник", list(labels.keys()),
                                    key="art_lib_pick")
                art_text_source = ("lib", labels[pick])
            else:
                st.caption("В библиотеке пока нет источников.")

        if st.button("📝 Сделать конспект", type="primary", key="make_summary"):
            try:
                with st.spinner("Извлекаю текст статьи…"):
                    if art_text_source is None:
                        raise ValueError("Не указан источник статьи.")
                    kind, val = art_text_source
                    if kind == "file":
                        art_text = source_service.extract_text(
                            filename=val.name, file_bytes=val.getvalue())
                        src_name = val.name
                    elif kind == "url":
                        art_text = source_service.extract_text(url=val)
                        src_name = val
                    else:
                        rec = db_service.get_materials_by_ids(USER_ID, [val])
                        art_text = rec[0]["content"] if rec else ""
                        src_name = rec[0]["name"] if rec else "источник"
                    if not art_text.strip():
                        raise ValueError("Не удалось получить текст статьи.")
                    if save_to_lib and kind in ("file", "url"):
                        db_service.add_material(
                            USER_ID, "file" if kind == "file" else "url",
                            src_name, art_text)
                with st.spinner("Готовлю конспект…"):
                    st.session_state.article_summary = generator.summarize_article(
                        art_text, article_type=art_type)
                    st.session_state.article_source_text = art_text
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")


# =====================================================================
#  ЗАГОЛОВОК ОСНОВНОЙ ОБЛАСТИ
# =====================================================================
def current_title() -> str:
    return (st.session_state.get("current_project_title")
            or st.session_state.get("p_podcast_name")
            or st.session_state.get("p_topic") or "")


project_started = bool(st.session_state.ideas or st.session_state.current_project_id)
show_summary = st.session_state.get("article_summary") is not None

if show_summary and not project_started:
    st.title("📝 Конспект статьи")
elif project_started and current_title():
    st.title(f"🎧 {current_title()}")
else:
    st.title("🎙️ Контент-планер подкастов")
    st.caption("ИИ-ассистент: идеи выпусков → контент-план → структура → описания")

if st.session_state.get("summary_material_text"):
    st.info("📎 К проекту подключён конспект статьи как материал-источник.")


# =====================================================================
#  ВЫВОД КОНСПЕКТА
# =====================================================================
summary = st.session_state.get("article_summary")
if summary:
    with st.container(border=True):
        if not (show_summary and not project_started):
            st.subheader("📝 Конспект статьи")
        if summary.get("title"):
            st.markdown(f"**{summary['title']}**")
        st.markdown("**Краткое содержание**")
        st.write(summary.get("summary", ""))
        if summary.get("key_points"):
            st.markdown("**Основные мысли**")
            for kp in summary["key_points"]:
                st.write(f"• {kp}")
        if summary.get("conclusions"):
            st.markdown("**Выводы**")
            for c in summary["conclusions"]:
                st.write(f"• {c}")
        if summary.get("note"):
            st.warning(summary["note"])

        st.download_button(
            "⬇️ Скачать конспект (Word)",
            data=export_service.summary_to_docx(summary),
            file_name="конспект_статьи.docx",
            mime=("application/vnd.openxmlformats-officedocument."
                  "wordprocessingml.document"))

        use_source = st.radio(
            "Что использовать для подкаста",
            ["конспект", "конспект + полная статья"],
            key="use_source_mode")
        if st.button("🎙️ Использовать для подкаста"):
            parts = ["=== Конспект статьи ===", summary.get("summary", "")]
            if summary.get("key_points"):
                parts.append("Основные мысли: " + "; ".join(summary["key_points"]))
            if summary.get("conclusions"):
                parts.append("Выводы: " + "; ".join(summary["conclusions"]))
            if use_source == "конспект + полная статья":
                parts.append("\n=== Полный текст статьи ===")
                parts.append(st.session_state.get("article_source_text", ""))
            st.session_state.summary_material_text = "\n".join(parts)[:20000]
            st.session_state.focus_required_fields = True
            st.success("Конспект подключён как источник. Заполните тематику "
                       "и аудиторию слева, затем нажмите «Сгенерировать идеи».")


# =====================================================================
#  БЛОК ПОДТВЕРЖДЕНИЯ УДАЛЕНИЯ
# =====================================================================
if st.session_state.get("confirm_delete_ids"):
    ids = st.session_state.confirm_delete_ids
    to_delete = db_service.get_materials_by_ids(USER_ID, ids)
    with st.container(border=True):
        st.error("⚠️ Подтверждение удаления источников")
        st.markdown("Будут удалены из вашей базы следующие источники:")
        st.markdown("\n".join(f"• {m['name']}" for m in to_delete))
        st.markdown("Вы **не сможете** использовать их более ни в текущем, "
                    "ни в других проектах. Действие необратимо.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Подтвердить удаление", type="primary"):
                for mid in ids:
                    db_service.delete_material(USER_ID, mid)
                st.session_state.confirm_delete_ids = None
                st.session_state.delete_mode = False
                st.success("Источники удалены.")
                st.rerun()
        with c2:
            if st.button("Отменить"):
                st.session_state.confirm_delete_ids = None
                st.rerun()


# =====================================================================
#  ПЛАНИРОВЩИК
# =====================================================================
if st.session_state.get("focus_required_fields"):
    st.info("👈 Заполните слева обязательные поля (тематика, аудитория) "
            "и нажмите «Сгенерировать идеи» — конспект будет учтён как источник.")

st.subheader("1. Идеи выпусков")
if st.button("💡 Сгенерировать идеи", type="primary", key="gen_ideas_main"):
    run_generate_ideas()

if st.session_state.ideas:
    st.caption("Отмеченные идеи войдут в контент-план. "
               "По умолчанию выбраны все — снимите лишние при необходимости.")
    selected_idea_indexes = []
    for i, idea in enumerate(st.session_state.ideas):
        with st.container(border=True):
            idea_default = i in st.session_state.selected_idea_indexes
            if st.checkbox(f"**{i + 1}. {idea.get('title', '—')}**",
                           value=idea_default, key=f"idea_{i}"):
                selected_idea_indexes.append(i)
            st.write(idea.get("angle", ""))
            st.caption(f"Формат: {idea.get('format', '—')} · "
                       f"Почему зайдёт: {idea.get('why_relevant', '—')}")
    st.session_state.selected_idea_indexes = selected_idea_indexes


# --- Шаг 2 ---
if st.session_state.ideas:
    st.subheader("2. Контент-план")
    if st.button("🗓️ Составить контент-план"):
        if settings_changed():
            st.session_state.regen_ask = ("plan", None)
            st.rerun()
        else:
            request_chain("plan", from_step="plan")

    if (st.session_state.get("regen_ask")
            and st.session_state.regen_ask[0] == "plan"):
        render_regen_dialog("plan", None)

if st.session_state.content_plan:
    for ep in st.session_state.content_plan:
        with st.container(border=True):
            st.markdown(f"**Выпуск {ep.get('episode_number')}** · "
                        f"🗓️ {ep.get('publish_date')}")
            st.markdown(f"**{ep.get('title')}**")
            st.write(ep.get("topic_summary", ""))


# --- Шаг 3 ---
if st.session_state.content_plan:
    st.subheader("3. Структура и описание выпуска")
    titles = [f"{ep.get('episode_number')}. {ep.get('title')}"
              for ep in st.session_state.content_plan]
    chosen = st.selectbox("Выберите выпуск", titles)
    idx = titles.index(chosen)
    episode = st.session_state.content_plan[idx]

    if st.button("🧩 Сгенерировать структуру и описание"):
        if settings_changed():
            st.session_state.regen_ask = ("structure", episode)
            st.rerun()
        else:
            request_chain("structure", from_step="structure", episode=episode)

    if (st.session_state.get("regen_ask")
            and st.session_state.regen_ask[0] == "structure"):
        render_regen_dialog("structure", st.session_state.regen_ask[1])

    if st.session_state.details:
        structure = st.session_state.details["structure"]
        description = st.session_state.details["description"]
        st.markdown("#### Структура эпизода")
        for block in structure.get("blocks", []):
            with st.container(border=True):
                st.markdown(f"**{block.get('name', '—')}** · "
                            f"_{block.get('duration', '')}_")
                st.caption(block.get("purpose", ""))
                for tp in block.get("talking_points", []):
                    st.write(f"• {tp}")
        st.markdown("#### Описание выпуска")
        st.text_area("Полное описание", description.get("full", ""), height=150)
        st.text_area("Краткое описание", description.get("short", ""), height=80)
        st.write(" ".join(description.get("hashtags", [])))


# --- Шаг 4: текст для озвучки ---
if st.session_state.get("details"):
    st.subheader("4. Текст для озвучки")
    st.caption("Полный произносимый текст выпуска по блокам структуры "
               "+ рекомендации по голосам для TTS.")
    st.checkbox(
        "Финальная вычитка текста", value=True, key="spoken_do_review",
        help="После сборки текста по блокам запускается дополнительный проход "
             "редактора по всему выпуску целиком: убирает повторные "
             "представления гостя и приветствия в середине, сокращает "
             "дословные повторы тезисов, унифицирует обозначения E/Z и "
             "сглаживает стыки блоков. Добавляет один запрос к модели "
             "(чуть дольше). Можно отключить для коротких выпусков.")
    spoken_btn = st.button("🎤 Сгенерировать текст для озвучки")
    # Место под индикатор прогресса — прямо под кнопкой.
    spoken_status_box = st.empty()


    if spoken_btn:
        episode = st.session_state.details.get("episode") or {}
        if settings_changed():
            st.session_state.regen_ask = ("spoken", episode)
            st.rerun()
        else:
            request_chain("spoken", from_step="spoken", episode=episode)

    if (st.session_state.get("regen_ask")
            and st.session_state.regen_ask[0] == "spoken"):
        render_regen_dialog("spoken", st.session_state.regen_ask[1])

    # Если стоит отложенное задание именно на озвучку — выполняем его здесь,
    # чтобы индикатор отрисовался под кнопкой.
    if _run_spoken_inline:
        execute_pending_job(spoken_status_box=spoken_status_box)

    if st.session_state.get("spoken_text"):
        st.markdown("#### Произносимый текст")

        # --- Диагностика: слова со смешанным алфавитом ---
        mixed = generator._collect_mixed_words(
            [l for l in st.session_state.spoken_text
             if l.get("speaker") != "__block__"])
        if mixed:
            uniq = sorted(set(mixed), key=str.lower)
            st.caption("⚠️ Найдены слова со смешанным алфавитом (русские + "
                       "латинские буквы в одном слове): "
                       + ", ".join(f"«{w}»" for w in uniq)
                       + ". Их стоит занести в словарь исправлений "
                         "(_MIXED_FIX_MAP в core/generator.py), чтобы они "
                         "чинились автоматически.")

        for line in st.session_state.spoken_text:
            speaker = (line.get("speaker") or "").strip()
            text = line.get("text", "")
            if speaker == "__block__":
                st.markdown(f"##### ▸ {text}")
                continue
            if speaker:
                st.markdown(f"**{speaker}:** {text}")
            else:
                st.write(text)

        voices = st.session_state.get("tts_voices")
        if voices:
            with st.expander("🎚️ Рекомендации по голосам для TTS"):
                for v in voices.get("voices", []):
                    st.markdown(f"**{v.get('role', 'Голос')}**")
                    st.write(f"Пол: {v.get('gender', '—')} · "
                             f"Возраст: {v.get('age', '—')} · "
                             f"Темп: {v.get('pace', '—')}")
                    st.write(f"Тембр: {v.get('timbre', '—')} · "
                             f"Эмоция: {v.get('emotion', '—')}")
                    if v.get("notes"):
                        st.caption(v["notes"])
                if voices.get("general"):
                    st.info(voices["general"])
                st.download_button(
                    "⬇️ Рекомендации по голосам (Word)",
                    data=export_service.tts_voices_to_docx(voices),
                    file_name="рекомендации_по_голосам.docx",
                    mime=("application/vnd.openxmlformats-officedocument."
                          "wordprocessingml.document"))

        ep_title = ""
        if st.session_state.details.get("episode"):
            ep_title = st.session_state.details["episode"].get("title", "")
        word_name = _safe_filename(
            f"Текст_озвучки__{ep_title or current_title()}"
            f"__{datetime.date.today().isoformat()}")
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "⬇️ Текст для озвучки (Word)",
                data=export_service.spoken_text_to_docx(
                    st.session_state.spoken_text, ep_title,
                    params=st.session_state.params),
                file_name=f"{word_name}.docx",
                mime=("application/vnd.openxmlformats-officedocument."
                      "wordprocessingml.document"))
        with col_b:
            tts_payload = {
                "episode_title": ep_title,
                "lines": [l for l in st.session_state.spoken_text
                          if l.get("speaker") != "__block__"],
                "voices": st.session_state.get("tts_voices"),
            }
            st.download_button(
                "⬇️ Для TTS (JSON по ролям)",
                data=json.dumps(tts_payload, ensure_ascii=False, indent=2),
                file_name=f"{_safe_filename('tts_' + (ep_title or 'script'))}.json",
                mime="application/json")


# =====================================================================
#  ЭКСПОРТ И СОХРАНЕНИЕ ПРОЕКТА
# =====================================================================
if st.session_state.content_plan:
    export = {
        "params": st.session_state.params,
        "ideas": st.session_state.ideas,
        "content_plan": st.session_state.content_plan,
        "details": st.session_state.details,
        "spoken_text": st.session_state.spoken_text,
        "tts_voices": st.session_state.tts_voices,
    }
    st.download_button(
        "💾 Скачать проект (JSON)",
        data=json.dumps(export, ensure_ascii=False, indent=2),
        file_name=f"{_safe_filename(current_title() or 'podcast_plan')}.json",
        mime="application/json")


if st.session_state.ideas:
    st.divider()
    st.subheader("💾 Сохранить проект")

    default_title = (st.session_state.get("current_project_title")
                     or st.session_state.p_podcast_name
                     or st.session_state.p_topic or "")
    proj_title = st.text_input("Название проекта", value=default_title)

    existing_id = st.session_state.get("current_project_id")
    has_changes = has_changes_vs_snapshot()

    col_save, col_saveas = st.columns(2)

    # --- Кнопка 1: Сохранить изменения (перезапись текущего проекта) ---
    with col_save:
        # Яркая и активная — только если проект существует И есть изменения.
        save_disabled = (not existing_id) or (not has_changes)
        if st.button("💾 Сохранить изменения",
                     type="primary" if has_changes else "secondary",
                     disabled=save_disabled,
                     key="save_existing"):
            if not proj_title.strip():
                st.error("Укажите название проекта.")
            else:
                db_service.update_project(USER_ID, existing_id,
                                          proj_title, build_project_data())
                st.session_state.current_project_title = proj_title
                st.session_state.saved_snapshot = make_snapshot()
                st.session_state.last_loaded_label = None
                st.success("Изменения сохранены в текущем проекте.")

    # --- Кнопка 2: Сохранить как новый проект ---
    with col_saveas:
        if st.button("🆕 Сохранить как новый проект", key="save_as_new"):
            if not proj_title.strip():
                st.error("Укажите название проекта.")
            else:
                new_id = db_service.save_project(
                    USER_ID, proj_title, build_project_data())
                st.session_state.current_project_id = new_id
                st.session_state.current_project_title = proj_title
                st.session_state.saved_snapshot = make_snapshot()
                st.session_state.last_loaded_label = None
                st.success(f"Создан новый проект: «{proj_title}».")

    # Подсказка о разнице между кнопками и состоянии изменений.
    if existing_id:
        if has_changes:
            st.caption("Есть несохранённые изменения. «Сохранить изменения» "
                       "перезапишет текущий проект. «Сохранить как новый "
                       "проект» создаст отдельную копию — удобно, чтобы из "
                       "одного источника сделать варианты для разных аудиторий.")
        else:
            st.caption("✅ Все изменения сохранены. Кнопка «Сохранить изменения» "
                       "станет активной, как только вы что-то измените.")
    else:
        st.caption("Проект ещё не сохранён. Нажмите «Сохранить как новый "
                   "проект», чтобы создать его в вашей базе.")
