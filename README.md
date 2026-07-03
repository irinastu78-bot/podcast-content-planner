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
  review/breakdown, storytelling, Q&A, and **fairytale** (a single narrator
  and a story arc instead of podcast blocks).
- **Tone & style:** friendly, expert, ironic, motivating, academic, fairytale.
  The fairytale style combines with any format (e.g. a scientific topic told in
  fairytale language for children). Child-safety rules turn on automatically for
  a child audience and can be overridden in the extra notes; the TTS voice is
  chosen as child or adult accordingly.
- **Spoken text by roles** (HOST / GUEST) with carried-over context between
  blocks and a final editorial pass: removes repeated introductions and
  mid-episode greetings, fixes role confusion and "thanking oneself", merges
  consecutive lines of the same speaker, trims verbatim repetitions, and unifies
  notation (e.g. E/Z isomers).
- **TTS voice recommendations** (gender, age, timbre, pace, emotion).
- **Smart regeneration:** when parameters change, the app asks from which step
  to rebuild (structure only / plan + structure / everything from ideas, etc.).
- **Project saving:** "Save changes" and "Save as new project" (handy for
  producing audience-specific variants from a single source).
- **Export:** spoken text and voice recommendations to Word (.docx), the article
  summary to Word, the project and TTS script to JSON. Word files include a
  technical header (podcast name, duration, audience, style, participant names).
- **Text quality control:** automatic cleanup of mixed-alphabet words
  (Cyrillic + Latin) with a user-editable replacement dictionary (stored in the
  DB, shared across the user's projects, editable in the UI, applied
  automatically) and diagnostics for unrecognized cases. The final editorial
  pass also fixes distorted Russian words, agreement errors, and narrative
  inconsistencies.


> Note: the generated content and the user interface are primarily in Russian.

## Tech Stack

- Python 3.10+
- Streamlit — web interface
- OpenAI API — text generation (default model: gpt-5.4-mini)
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
    │   ├── db_service.py           # SQLite: users, materials, projects, mixed-word dictionary
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
       OPENAI_MODEL=gpt-5.4-mini        # optional, default: gpt-5.4-mini
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
- Child-safety rules are applied automatically when the audience is detected as
  a children's audience (for any format, not only fairytale), and can be
  overridden via the extra notes.


## Notes & Limitations

- Generation depends on the external OpenAI API: quality and speed depend on the
  selected model; occasional response-parsing errors are possible.
- The final editorial pass reduces defects, but a manual review before recording
  is recommended (especially for factual nuances).
- Source text sent to the model is truncated (~12,000 characters) to limit
  prompt size.

**Screenshots:** <br>
<a href="images/gen_ideas.png" target="_blank">
  <img src="images/gen_ideas.png" alt="Main app screen with filled podcast parameters: title, duration, audience, format, style, guest name" title="Main app screen with filled podcast parameters: title, duration, audience, format, style, guest name" height="100">
</a>
<a href="images/menu1.png" target="_blank">
  <img src="images/menu1.png" alt="Podcast parameters menu for scientific article (part 1)" title="Podcast parameters menu for scientific article (part 1)" height="100">
</a>
<a href="images/menu2.png" target="_blank">
  <img src="images/menu2.png" alt="Podcast parameters menu for scientific article (part 2)" title="Podcast parameters menu for scientific article (part 2)" height="100">
</a>
<a href="images/menu3.png" target="_blank">
  <img src="images/menu3.png" alt="Uploading source file (PDF/DOCX book)" title="Uploading source file (PDF/DOCX book)" height="100">
</a>
<a href="images/menu4.png" target="_blank">
  <img src="images/menu4.png" alt="Adding article link as a source" title="Adding article link as a source" height="100">
</a>
<a href="images/conspect.png" target="_blank">
  <img src="images/conspect.png" alt="Completed article summary that can be used as a podcast source" title="Completed article summary that can be used as a podcast source" height="100">
</a>
<a href="images/ideas_chem.png" target="_blank">
  <img src="images/ideas_chem.png" alt="Generated episode ideas" title="Generated episode ideas" height="100">
</a>
<a href="images/content_chem.png" target="_blank">
  <img src="images/content_chem.png" alt="Content plan for multiple episodes" title="Content plan for multiple episodes" height="100">
</a>
<a href="images/struc_chem.png" target="_blank">
  <img src="images/struc_chem.png" alt="Episode structure with blocks and timing" title="Episode structure with blocks and timing" height="100">
</a>
<a href="images/tts_screen.png" target="_blank">
  <img src="images/tts_screen.png" alt="Voiceover script with role breakdown and generation progress indicator" title="Voiceover script with role breakdown and generation progress indicator" height="100">
</a>
<a href="images/tts_rec.png" target="_blank">
  <img src="images/tts_rec.png" alt="Voice recommendations for speech synthesis" title="Voice recommendations for speech synthesis" height="100">
</a>
<a href="images/tts_word.png" target="_blank">
  <img src="images/tts_word.png" alt="Completed Word file with technical header: podcast title, duration, audience, style, participants" title="Completed Word file with technical header: podcast title, duration, audience, style, participants" height="100">
</a>
<a href="images/ideas_tale.png" target="_blank">
  <img src="images/ideas_tale.png" alt="Example of using 'fairy tale' format and style: episode ideas" title="Example of using 'fairy tale' format and style: episode ideas" height="100">
</a>
<a href="images/tts_tale.png" target="_blank">
  <img src="images/tts_tale.png" alt="Example of using 'fairy tale' format and style: voiceover script" title="Example of using 'fairy tale' format and style: voiceover script" height="100">
</a>
