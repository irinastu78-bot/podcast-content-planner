# 🎙️ Podcast Content Planner

An AI assistant for planning podcasts — from episode ideas all the way to a
ready-to-voice script and TTS voice recommendations.

A web app built with [Streamlit](https://streamlit.io/). You set the podcast
parameters, and the system sequentially generates ideas, a content plan, an
episode structure, a description, and the final spoken text split by roles.

🇷🇺 Russian version: [README.ru.md](README.ru.md)

## Features

- **User authentication** (login/password); each user has their own projects
  and source library.
- **Five-step generation pipeline:** episode ideas → content plan → episode
  structure → description → spoken text.
- **Source materials:** upload files (txt, md, pdf, docx, pptx, xlsx) or fetch
  articles by URL; ideas and texts can be grounded in them.
- **Article summarizer** as a standalone tool (popular and scientific articles);
  the result can be attached as a source for the podcast.
- **Episode formats:** guest interview, two-host discussion, solo monologue,
  review/breakdown, storytelling, Q&A.
- **Tone & style:** friendly, expert, ironic, motivating, academic, and
  fairytale (with a safe, child-appropriate default voice).
- **Spoken text by roles** (HOST / GUEST) with carried-over context between
  blocks and a final editorial pass (removes repeated introductions, mid-episode
  greetings, verbatim repetitions, and unifies notation such as E/Z isomers).
- **TTS voice recommendations** (gender, age, timbre, pace, emotion).
- **Smart regeneration:** when parameters change, the app asks from which step
  to rebuild (structure only / plan + structure / everything from ideas, etc.).
- **Project saving:** "Save changes" and "Save as new project" (handy for
  producing audience-specific variants from a single source).
- **Export:** spoken text and voice recommendations to Word (.docx), the article
  summary to Word, the project and TTS script to JSON. Word files include a
  technical header (podcast name, duration, audience, style, participant names).
- **Text quality control:** automatic cleanup of mixed-alphabet words
  (Cyrillic + Latin) with diagnostics for unrecognized cases.

> Note: the generated content and the user interface are primarily in Russian.

## Tech Stack

- Python 3.10+
- Streamlit — web interface
- OpenAI API — text generation (default model: gpt-4o-mini)
- SQLite — persistent storage (podcast_planner.db)
- python-docx — Word export
- pypdf, python-docx, python-pptx, openpyxl — text extraction from files
- trafilatura — article text extraction from URLs
- python-dotenv — environment variables

## Project Structure

    .
    ├── app.py                      # Streamlit web interface, all UI and orchestration
    ├── core/
    │   ├── generator.py            # Multi-step generation logic
    │   └── prompts.py              # All system prompts
    ├── services/
    │   ├── auth_service.py         # Registration and login
    │   ├── db_service.py           # SQLite: users, materials, projects
    │   ├── export_service.py       # Word (.docx) export
    │   ├── llm_service.py          # OpenAI call wrapper, JSON parsing
    │   └── source_service.py       # Text extraction from files and URLs
    ├── requirements.txt
    ├── .env                        # Environment variables (do NOT commit)
    └── README.md

## Installation & Run

1. Clone the repository and enter the project directory.

2. Create and activate a virtual environment:

       python -m venv venv
       source venv/bin/activate        # Windows: venv\Scripts\activate

3. Install dependencies:

       pip install -r requirements.txt

4. Create a `.env` file in the project root:

       OPENAI_API_KEY=sk-...           # required
       OPENAI_MODEL=gpt-4o-mini        # optional, default: gpt-4o-mini
       DB_PATH=podcast_planner.db      # optional, default: podcast_planner.db

5. Run the app:

       streamlit run app.py

6. Open the URL printed by Streamlit (default: http://localhost:8501).

On first launch, create an account on the "Регистрация" (Register) tab.

## Usage

1. **Podcast parameters** (left sidebar): topic and audience are required; the
   advanced section covers podcast name, participant names, tone, duration,
   number of ideas and episodes, start date, and extra notes.
2. **Source material** (optional): upload a file/URL, pick from the library, or
   summarize an article and attach it.
3. Click **"Сгенерировать идеи"** (Generate ideas), then proceed step by step:
   content plan → structure → spoken text.
4. Download the result (Word / JSON) and save the project.

> **Extra notes** are taken into account at every generation step. Use them for
> free-form instructions: how to introduce the guest, "this is the first / not
> the first episode of the series", what to include or avoid.

## Deployment

- Run behind a reverse proxy (e.g. nginx), pointing to the Streamlit port.
- Bind the address and port explicitly:

      streamlit run app.py --server.port 8501 --server.address 0.0.0.0

- Keep `.env` and the SQLite database out of public access and include them in
  backups. The `OPENAI_API_KEY` must never be committed to the repository.
- The database file is created automatically on first launch.

## Security & Safety

- Passwords are stored hashed (see `auth_service.py`).
- Foreign keys cascade: deleting a user removes their materials and projects.
- The "fairytale" tone is constrained by default to produce content that is
  safe and appropriate for children.

## Notes & Limitations

- Generation depends on the external OpenAI API: quality and speed depend on the
  selected model; occasional response-parsing errors are possible.
- The final editorial pass reduces defects, but a manual review before recording
  is recommended (especially for factual nuances).
- Source text sent to the model is truncated (~12,000 characters) to limit
  prompt size.
