"""Tech stack: what a repo is built with, read from its own manifests.

Each directory with a manifest (package.json, requirements.txt, pyproject.toml, go.mod, Cargo.toml,
Gemfile, composer.json, pom.xml, build.gradle, *.csproj) is a workspace — except Gradle, whose modules
join the build that holds settings.gradle, with libs.* aliases read from gradle/libs.versions.toml; its dependencies are
sorted into categories (frameworks, databases, AI, testing …). Dockerfiles, compose files, CI
workflows and deploy configs form one more branch for the whole repo. Every entry cites the line
that declares it, so the tree can be checked like any answer. No language model is used, so the
stack is free and quick to build.
"""
import json
import logging
import os
import re

from ..store import RepoStore

log = logging.getLogger(__name__)

CATEGORIES = [
    ("runtime", "Languages & runtimes"),
    ("framework", "Frameworks"),
    ("ui", "UI & styling"),
    ("data", "Data, state & validation"),
    ("database", "Databases & ORMs"),
    ("auth", "Auth & security"),
    ("ai", "AI & ML"),
    ("testing", "Testing & quality"),
    ("tooling", "Build & tooling"),
    ("infra", "Infrastructure & deploy"),
    ("ci", "CI/CD"),
    ("other", "Other libraries"),
]
_ORDER = {k: i for i, (k, _) in enumerate(CATEGORIES)}

# package name → (display name, category). A trailing "*" matches a scope or prefix.
_KNOWN = {
    "framework": {
        "next": "Next.js", "react": "React", "vue": "Vue", "nuxt": "Nuxt", "svelte": "Svelte",
        "@sveltejs/kit": "SvelteKit", "@angular/core": "Angular", "express": "Express", "fastify": "Fastify",
        "koa": "Koa", "@nestjs/core": "NestJS", "hono": "Hono", "@remix-run/*": "Remix", "astro": "Astro",
        "solid-js": "SolidJS", "electron": "Electron", "@tauri-apps/*": "Tauri", "@capacitor/*": "Capacitor",
        "react-native": "React Native", "expo": "Expo", "remotion": "Remotion", "@remotion/*": "Remotion",
        "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "starlette": "Starlette",
        "uvicorn": "Uvicorn", "gunicorn": "Gunicorn", "streamlit": "Streamlit", "gradio": "Gradio",
        "aiohttp": "aiohttp", "tornado": "Tornado", "djangorestframework": "Django REST framework",
        "github.com/gin-gonic/gin": "Gin", "github.com/labstack/echo*": "Echo", "github.com/gofiber/fiber*": "Fiber",
        "github.com/gorilla/mux": "Gorilla mux", "github.com/go-chi/chi*": "chi", "google.golang.org/grpc": "gRPC",
        "tokio": "Tokio", "axum": "Axum", "actix-web": "Actix Web", "rocket": "Rocket", "tauri": "Tauri", "tauri-*": "Tauri",
        "rails": "Ruby on Rails", "sinatra": "Sinatra", "puma": "Puma",
        "laravel/framework": "Laravel", "symfony/*": "Symfony",
        "spring-boot*": "Spring Boot", "Microsoft.AspNetCore*": "ASP.NET Core",
    },
    "ui": {
        "tailwindcss": "Tailwind CSS", "framer-motion": "Framer Motion", "motion": "Motion",
        "@radix-ui/*": "Radix UI", "@base-ui-components/*": "Base UI", "@base-ui/*": "Base UI",
        "@mui/*": "MUI", "@chakra-ui/*": "Chakra UI", "styled-components": "styled-components",
        "@emotion/*": "Emotion", "lucide-react": "Lucide icons", "sonner": "Sonner", "next-themes": "next-themes",
        "bootstrap": "Bootstrap", "sass": "Sass", "@headlessui/*": "Headless UI", "recharts": "Recharts",
        "d3": "D3", "three": "three.js", "@react-three/*": "React Three Fiber", "chart.js": "Chart.js",
        "mermaid": "Mermaid", "react-markdown": "react-markdown", "@tiptap/*": "Tiptap",
        "class-variance-authority": "class-variance-authority", "tailwind-merge": "tailwind-merge",
        "clsx": "clsx", "cmdk": "cmdk", "shiki": "Shiki", "highlight.js": "highlight.js", "prismjs": "Prism",
    },
    "data": {
        "@tanstack/react-query": "TanStack Query", "swr": "SWR", "axios": "Axios", "redux": "Redux",
        "@reduxjs/toolkit": "Redux Toolkit", "zustand": "Zustand", "jotai": "Jotai", "mobx": "MobX",
        "zod": "Zod", "yup": "Yup", "graphql": "GraphQL", "@apollo/*": "Apollo", "@trpc/*": "tRPC",
        "react-hook-form": "React Hook Form", "idb": "idb (IndexedDB)", "dexie": "Dexie",
        "pydantic": "Pydantic", "pydantic-settings": "pydantic-settings", "requests": "Requests",
        "httpx": "HTTPX", "marshmallow": "marshmallow", "pandas": "pandas", "numpy": "NumPy", "polars": "Polars",
        "celery": "Celery", "python-multipart": "python-multipart", "pyyaml": "PyYAML",
        "serde": "Serde", "reqwest": "reqwest",
    },
    "database": {
        "prisma": "Prisma", "@prisma/client": "Prisma", "drizzle-orm": "Drizzle ORM", "typeorm": "TypeORM",
        "sequelize": "Sequelize", "mongoose": "Mongoose", "mongodb": "MongoDB", "pg": "PostgreSQL (node-postgres)",
        "mysql2": "MySQL", "redis": "Redis", "ioredis": "Redis", "@supabase/*": "Supabase", "supabase": "Supabase",
        "firebase": "Firebase", "better-sqlite3": "SQLite", "knex": "Knex", "@neondatabase/*": "Neon",
        "sqlalchemy": "SQLAlchemy", "sqlmodel": "SQLModel", "alembic": "Alembic", "psycopg": "PostgreSQL (psycopg)",
        "psycopg2": "PostgreSQL (psycopg2)", "psycopg2-binary": "PostgreSQL (psycopg2)", "asyncpg": "PostgreSQL (asyncpg)",
        "pymongo": "MongoDB", "motor": "MongoDB (Motor)", "pgvector": "pgvector", "peewee": "Peewee",
        "tortoise-orm": "Tortoise ORM", "chromadb": "Chroma", "pinecone-client": "Pinecone", "pinecone": "Pinecone",
        "faiss-cpu": "FAISS", "qdrant-client": "Qdrant",
        "gorm.io/gorm": "GORM", "github.com/jackc/pgx*": "PostgreSQL (pgx)", "github.com/redis/go-redis*": "Redis",
        "sqlx": "SQLx", "diesel": "Diesel", "hibernate*": "Hibernate",
        "Microsoft.EntityFrameworkCore*": "Entity Framework Core",
    },
    "auth": {
        "next-auth": "NextAuth.js", "@auth/*": "Auth.js", "passport": "Passport", "jsonwebtoken": "JSON Web Tokens",
        "jose": "jose (JWT)", "bcrypt": "bcrypt", "bcryptjs": "bcrypt", "@clerk/*": "Clerk", "helmet": "Helmet",
        "passlib": "passlib", "pyjwt": "PyJWT", "python-jose": "python-jose", "cryptography": "cryptography",
        "authlib": "Authlib", "slowapi": "SlowAPI (rate limits)", "limits": "limits (rate limits)",
        "google-auth": "Google Auth", "github.com/golang-jwt/jwt*": "JSON Web Tokens", "devise": "Devise",
    },
    "ai": {
        "openai": "OpenAI SDK", "@anthropic-ai/sdk": "Anthropic SDK", "anthropic": "Anthropic SDK",
        "ai": "Vercel AI SDK", "@ai-sdk/*": "Vercel AI SDK", "langchain": "LangChain", "@langchain/*": "LangChain",
        "langchain-*": "LangChain", "langgraph": "LangGraph", "llama-index": "LlamaIndex",
        "@google/generative-ai": "Gemini SDK", "google-generativeai": "Gemini SDK", "google-genai": "Gemini SDK",
        "@aws-sdk/client-bedrock*": "Amazon Bedrock", "transformers": "Hugging Face Transformers",
        "@xenova/transformers": "Transformers.js", "@huggingface/*": "Hugging Face", "huggingface-hub": "Hugging Face Hub",
        "torch": "PyTorch", "torchvision": "torchvision", "tensorflow": "TensorFlow", "@tensorflow/*": "TensorFlow.js",
        "keras": "Keras", "scikit-learn": "scikit-learn", "sentence-transformers": "Sentence Transformers",
        "tiktoken": "tiktoken", "xgboost": "XGBoost", "lightgbm": "LightGBM", "opencv-python": "OpenCV",
        "opencv-python-headless": "OpenCV", "spacy": "spaCy", "nltk": "NLTK", "onnxruntime": "ONNX Runtime",
        "onnxruntime-web": "ONNX Runtime", "ollama": "Ollama", "litellm": "LiteLLM", "amazon-transcribe": "Amazon Transcribe", "mcp": "Model Context Protocol",
        "@modelcontextprotocol/*": "Model Context Protocol",
    },
    "testing": {
        "jest": "Jest", "vitest": "Vitest", "@playwright/test": "Playwright", "playwright": "Playwright",
        "cypress": "Cypress", "@testing-library/*": "Testing Library", "mocha": "Mocha", "chai": "Chai",
        "eslint": "ESLint", "prettier": "Prettier", "@biomejs/biome": "Biome", "pytest": "pytest",
        "pytest-*": "pytest plugins", "coverage": "coverage.py", "ruff": "Ruff", "black": "Black", "mypy": "mypy",
        "flake8": "Flake8", "pylint": "Pylint", "hypothesis": "Hypothesis", "tox": "tox", "pre-commit": "pre-commit",
        "github.com/stretchr/testify": "Testify", "rspec*": "RSpec", "phpunit/phpunit": "PHPUnit",
        "junit*": "JUnit", "mockito*": "Mockito", "xunit*": "xUnit", "nunit*": "NUnit",
    },
    "tooling": {
        "typescript": "TypeScript", "vite": "Vite", "webpack": "webpack", "esbuild": "esbuild", "turbo": "Turborepo",
        "nx": "Nx", "@babel/core": "Babel", "rollup": "Rollup", "postcss": "PostCSS", "autoprefixer": "Autoprefixer",
        "tsup": "tsup", "@swc/core": "SWC", "nodemon": "nodemon", "ts-node": "ts-node", "tsx": "tsx",
        "@tauri-apps/cli": "Tauri CLI", "@capacitor/cli": "Capacitor CLI", "setuptools": "setuptools",
        "hatchling": "Hatch", "poetry-core": "Poetry", "typer": "Typer", "click": "Click", "rich": "Rich",
        "python-dotenv": "python-dotenv", "dotenv": "dotenv", "github.com/spf13/cobra": "Cobra", "clap": "clap",
        "lombok*": "Lombok",
    },
    "infra": {
        "@vercel/*": "Vercel", "@aws-sdk/*": "AWS SDK", "aws-sdk": "AWS SDK", "boto3": "AWS SDK (boto3)",
        "botocore": "AWS SDK (botocore)", "@sentry/*": "Sentry", "sentry-sdk": "Sentry", "docker": "Docker SDK",
        "kubernetes": "Kubernetes client", "stripe": "Stripe", "resend": "Resend", "nodemailer": "Nodemailer",
        "twilio": "Twilio", "@google-cloud/*": "Google Cloud", "google-cloud-*": "Google Cloud",
        "azure-*": "Azure SDK", "@azure/*": "Azure SDK", "posthog": "PostHog", "posthog-js": "PostHog",
        "opentelemetry-*": "OpenTelemetry", "@opentelemetry/*": "OpenTelemetry", "prometheus-client": "Prometheus",
    },
}
# Gradle (Kotlin, Android, JVM): matched on "group:artifact" or a plugin id, before the bare artifact
_KNOWN_GRADLE = {
    "runtime": {
        "org.jetbrains.kotlin.android": "Kotlin", "org.jetbrains.kotlin.jvm": "Kotlin",
        "org.jetbrains.kotlin:kotlin-stdlib*": "Kotlin",
    },
    "framework": {
        "org.jetbrains.kotlin.multiplatform": "Kotlin Multiplatform", "com.android.application": "Android",
        "com.android.library": "Android", "com.android.kotlin.multiplatform.library": "Android",
        "org.springframework.boot*": "Spring Boot", "io.ktor:ktor-server*": "Ktor server",
        "io.quarkus*": "Quarkus", "io.micronaut*": "Micronaut",
    },
    "ui": {
        "org.jetbrains.compose*": "Compose Multiplatform", "compose.*": "Compose Multiplatform",
        "androidx.compose.material3*": "Material 3 (Compose)", "androidx.compose*": "Jetpack Compose",
        "androidx.activity:activity-compose": "Jetpack Compose", "androidx.navigation*": "Navigation",
        "androidx.appcompat*": "AppCompat", "com.google.android.material*": "Material Components",
        "io.coil-kt*": "Coil", "com.github.bumptech.glide*": "Glide", "org.jetbrains.kotlin.plugin.compose": "Compose compiler",
    },
    "data": {
        "org.jetbrains.kotlinx:kotlinx-coroutines*": "Kotlin Coroutines",
        "org.jetbrains.kotlinx:kotlinx-serialization*": "kotlinx.serialization",
        "org.jetbrains.kotlin.plugin.serialization": "kotlinx.serialization",
        "org.jetbrains.kotlinx:kotlinx-datetime*": "kotlinx-datetime", "androidx.lifecycle*": "Lifecycle & ViewModel",
        "org.jetbrains.androidx.lifecycle*": "Lifecycle & ViewModel", "io.insert-koin*": "Koin",
        "com.google.dagger*": "Dagger / Hilt", "com.google.dagger.hilt.android": "Dagger / Hilt",
        "com.squareup.retrofit2*": "Retrofit", "com.squareup.okhttp3*": "OkHttp", "io.ktor*": "Ktor client",
        "com.google.code.gson*": "Gson", "com.squareup.moshi*": "Moshi", "androidx.datastore*": "DataStore",
        "androidx.paging*": "Paging", "androidx.work*": "WorkManager",
    },
    "database": {
        "androidx.room*": "Room", "app.cash.sqldelight*": "SQLDelight", "io.realm*": "Realm",
        "org.jetbrains.exposed*": "Exposed",
    },
    "auth": {"com.google.firebase:firebase-auth*": "Firebase Auth"},
    "infra": {"com.google.firebase*": "Firebase", "com.google.gms.google-services": "Firebase"},
    "testing": {
        "org.jetbrains.kotlin:kotlin-test*": "Kotlin Test", "androidx.test.espresso*": "Espresso",
        "androidx.test*": "AndroidX Test", "androidx.compose.ui:ui-test*": "Compose UI tests",
        "io.mockk*": "MockK", "io.kotest*": "Kotest", "app.cash.turbine*": "Turbine",
        "org.robolectric*": "Robolectric", "junit:junit": "JUnit", "org.junit*": "JUnit",
    },
    "tooling": {
        "androidx.core*": "AndroidX Core", "com.google.devtools.ksp": "KSP",
        "org.jetbrains.compose.hot-reload": "Compose Hot Reload",
        "com.vanniktech.maven.publish": "Maven Central publishing", "maven-publish": "Maven publishing",
        "org.jetbrains.dokka": "Dokka", "io.gitlab.arturbosch.detekt": "detekt",
        "org.jlleitschuh.gradle.ktlint": "ktlint", "com.diffplug.spotless": "Spotless",
    },
}
_EXACT: dict[str, tuple[str, str]] = {}
_PREFIX: list[tuple[str, str, str]] = []
for _cat, _names in [*_KNOWN_GRADLE.items(), *_KNOWN.items()]:
    for _k, _label in _names.items():
        if _k.endswith("*"):
            _PREFIX.append((_k[:-1].lower(), _label, _cat))
        else:
            _EXACT.setdefault(_k.lower(), (_label, _cat))
_PREFIX.sort(key=lambda p: -len(p[0]))

# images in compose files / Dockerfiles that name a service, not just a base OS
_IMAGES = {
    "postgres": ("PostgreSQL", "database"), "pgvector/pgvector": ("PostgreSQL + pgvector", "database"),
    "mysql": ("MySQL", "database"), "mariadb": ("MariaDB", "database"), "mongo": ("MongoDB", "database"),
    "redis": ("Redis", "database"), "valkey/valkey": ("Valkey", "database"), "elasticsearch": ("Elasticsearch", "database"),
    "opensearchproject/opensearch": ("OpenSearch", "database"), "qdrant/qdrant": ("Qdrant", "database"),
    "nginx": ("nginx", "infra"), "traefik": ("Traefik", "infra"), "caddy": ("Caddy", "infra"),
    "rabbitmq": ("RabbitMQ", "infra"), "minio/minio": ("MinIO", "infra"), "adminer": ("Adminer", "tooling"),
    "localstack/localstack": ("LocalStack", "infra"), "ollama/ollama": ("Ollama", "ai"),
}

_LANGS = {
    ".py": "Python", ".ipynb": "Jupyter notebooks", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".kt": "Kotlin", ".kts": "Kotlin", ".swift": "Swift", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".c": "C", ".h": "C", ".dart": "Dart", ".scala": "Scala",
    ".sql": "SQL", ".sh": "Shell", ".bash": "Shell", ".css": "CSS", ".scss": "SCSS", ".html": "HTML",
    ".vue": "Vue", ".svelte": "Svelte", ".lua": "Lua", ".r": "R", ".ex": "Elixir", ".exs": "Elixir",
}

_MANIFESTS = ("package.json", "requirements.txt", "pyproject.toml", "Pipfile", "go.mod", "Cargo.toml",
              "Gemfile", "composer.json", "pom.xml", "build.gradle", "build.gradle.kts")


def classify(name: str) -> tuple[str, str] | None:
    """(display name, category) for a known package, else None."""
    n = name.strip().lower()
    if n in _EXACT:
        return _EXACT[n]
    for p, label, cat in _PREFIX:
        if n.startswith(p):
            return label, cat
    return None


def _is_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (name in _MANIFESTS or name.endswith(".csproj")
            or (name.startswith("requirements") and name.endswith(".txt")))


def _cite(file: str, line: int) -> dict:
    return {"file": file, "start_line": line, "end_line": line}


def _find(lines: list[str], pattern: str, start: int = 0) -> int:
    """1-based number of the first line matching `pattern`, else 1."""
    rx = re.compile(pattern)
    for i in range(start, len(lines)):
        if rx.search(lines[i]):
            return i + 1
    return 1


# --- one parser per manifest kind: each yields (package, version, line, dev) ---

def _package_json(lines: list[str]):
    try:
        data = json.loads("\n".join(lines))
    except ValueError:
        return
    for key, dev in (("dependencies", False), ("devDependencies", True), ("peerDependencies", False),
                     ("optionalDependencies", False)):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        at = _find(lines, rf'"{key}"\s*:') - 1
        for name, ver in block.items():
            yield name, str(ver), _find(lines, rf'"{re.escape(name)}"\s*:', at), dev
    engines = data.get("engines")
    if isinstance(engines, dict) and engines.get("node"):
        yield "@runtime/node", str(engines["node"]), _find(lines, r'"node"\s*:'), False
    if isinstance(data.get("packageManager"), str):
        pm, _, ver = data["packageManager"].partition("@")
        yield f"@runtime/{pm}", ver.split("+")[0], _find(lines, r'"packageManager"'), False


_REQ = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*([^;#]*)")


def _requirements(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not s or s.startswith(("#", "-", "git+", "http")):
            continue
        m = _REQ.match(s)
        if m:
            yield m.group(1), m.group(2).strip(), i, False


def _pyproject(lines: list[str]):
    table, in_array, dev = "", False, False
    for i, ln in enumerate(lines, 1):
        s = ln.split("#", 1)[0].strip()
        if not s:
            continue
        if s.startswith("[") and not in_array:
            table = s.strip("[]").strip()
            dev = "dev" in table or "test" in table
            continue
        if table == "project" and s.startswith("requires-python"):
            yield "@runtime/python", s.split("=", 1)[1].strip().strip("\"'"), i, False
            continue
        if in_array or (table in ("project", "project.optional-dependencies", "dependency-groups")
                        and re.match(r"^[\w-]+\s*=\s*\[", s)):
            if not in_array:
                key = s.split("=", 1)[0].strip()
                if table == "project" and key != "dependencies":
                    continue
                in_array = True
                s = s.split("[", 1)[1]
            for q in re.findall(r"[\"']([^\"']+)[\"']", s):
                m = _REQ.match(q)
                if m:
                    yield m.group(1), m.group(2).strip(), i, dev or table != "project"
            if "]" in s:
                in_array = False
            continue
        if table.startswith("tool.poetry") and table.endswith("dependencies"):
            m = re.match(r"^([\w.-]+)\s*=\s*(.+)$", s)
            if m:
                ver = re.sub(r"^\{?\s*(?:version\s*=\s*)?[\"']?([^\"',}]*).*$", r"\1", m.group(2))
                if m.group(1) == "python":
                    yield "@runtime/python", ver, i, False
                else:
                    yield m.group(1), ver, i, "dev" in table or "group" in table


def _toml_tables(lines: list[str], want) -> list:
    """`name = "1.0"` / `name = { version = "1.0" }` lines in tables chosen by `want(table)`."""
    out, table = [], ""
    for i, ln in enumerate(lines, 1):
        s = ln.split("#", 1)[0].strip()
        if s.startswith("["):
            table = s.strip("[]").strip()
            continue
        m = re.match(r"^([\w.-]+)\s*=\s*(.+)$", s)
        if m and want(table):
            ver = re.search(r"[\"']([^\"']*)[\"']", m.group(2))
            out.append((m.group(1), ver.group(1) if ver else "", i, "dev" in table))
    return out


def _pipfile(lines):
    return _toml_tables(lines, lambda t: t in ("packages", "dev-packages"))


def _cargo(lines):
    out = _toml_tables(lines, lambda t: t.endswith("dependencies"))
    out += [("@runtime/rust", v, i, False) for k, v, i, _ in _toml_tables(lines, lambda t: t == "package")
            if k == "rust-version"]
    return out


def _go_mod(lines: list[str]):
    block = False
    for i, ln in enumerate(lines, 1):
        s = ln.split("//", 1)[0].strip()
        if s.startswith("go ") and not block:
            yield "@runtime/go", s[3:].strip(), i, False
        elif s.startswith("require ("):
            block = True
        elif block and s == ")":
            block = False
        elif block or s.startswith("require "):
            parts = s.replace("require ", "").split()
            if len(parts) >= 2:
                yield parts[0], parts[1], i, "indirect" in ln


def _gemfile(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        m = re.match(r"""^\s*gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?""", ln)
        if m:
            yield m.group(1), m.group(2) or "", i, False
        m = re.match(r"""^\s*ruby\s+['"]([^'"]+)['"]""", ln)
        if m:
            yield "@runtime/ruby", m.group(1), i, False


def _composer(lines: list[str]):
    try:
        data = json.loads("\n".join(lines))
    except ValueError:
        return
    for key, dev in (("require", False), ("require-dev", True)):
        block = data.get(key)
        if isinstance(block, dict):
            at = _find(lines, rf'"{key}"\s*:') - 1
            for name, ver in block.items():
                line = _find(lines, rf'"{re.escape(name)}"\s*:', at)
                yield ("@runtime/php" if name == "php" else name), str(ver), line, dev


def _maven(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        m = re.search(r"<artifactId>([^<]+)</artifactId>", ln)
        if m:
            yield m.group(1), "", i, False


_GRADLE_CONF = r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation|androidTestImplementation|" \
               r"debugImplementation|testRuntimeOnly|kapt|ksp|annotationProcessor|coreLibraryDesugaring)"


def _accessor(key: str) -> str:
    """Catalog key → how build files name it: "androidx-activity_compose" → "androidx.activity.compose"."""
    return re.sub(r"[-_.]", ".", key).lower()


def version_catalog(lines: list[str]) -> dict:
    """gradle/libs.versions.toml → {"libraries": {accessor: (group:artifact, version)}, "plugins": {…}}."""
    versions: dict[str, str] = {}
    entries: dict[str, list] = {"libraries": [], "plugins": [], "bundles": []}
    table = ""
    for raw in lines:
        ln = raw.split("#", 1)[0].strip()
        if m := re.match(r"\[([\w-]+)\]$", ln):
            table = m.group(1)
            continue
        m = re.match(r"""([\w.-]+)\s*=\s*(.+)$""", ln)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if table == "versions":
            v = re.search(r'"([^"]+)"', val)
            versions[key] = v.group(1) if v else ""
        elif table in entries:
            entries[table].append((key, val))

    def field(val, name):
        f = re.search(name + r'\s*=\s*"([^"]+)"', val)
        return f.group(1) if f else ""

    def ver(val):
        if ref := field(val, r"version\.ref"):
            return versions.get(ref, "")
        return field(val, r"(?<![.\w])version")

    out: dict[str, dict] = {"libraries": {}, "plugins": {}, "bundles": {}}
    for key, val in entries["libraries"]:
        if val.startswith('"'):  # "group:artifact:version"
            parts = val.strip('"').split(":")
            coord, v = ":".join(parts[:2]), (parts[2] if len(parts) > 2 else "")
        else:
            coord = field(val, "module") or f'{field(val, "group")}:{field(val, "name")}'
            v = ver(val)
        out["libraries"][_accessor(key)] = (coord, v)
    for key, val in entries["plugins"]:
        pid, v = (val.strip('"').split(":") + [""])[:2] if val.startswith('"') else (field(val, "id"), ver(val))
        out["plugins"][_accessor(key)] = (pid, v)
    for key, val in entries["bundles"]:
        out["bundles"][_accessor(key)] = [_accessor(k) for k in re.findall(r'"([^"]+)"', val)]
    return out


def _gradle(lines: list[str], catalog: dict | None = None):
    """Dependencies and plugins of a build.gradle(.kts), resolving version-catalog aliases (libs.*)."""
    cat = catalog or {"libraries": {}, "plugins": {}, "bundles": {}}
    for i, ln in enumerate(lines, 1):
        code = ln.split("//", 1)[0]
        test = bool(re.search(r"\b(?:test|androidTest)\w*", code.split("(")[0], re.I))
        if m := re.search(_GRADLE_CONF + r"""\s*\(?\s*(?:platform\s*\(\s*)?['"]([^:'"]+):([^:'"]+)(?::([^'"]+))?['"]""", code):
            yield f"{m.group(1)}:{m.group(2)}", m.group(3) or "", i, test
        elif m := re.search(_GRADLE_CONF + r"\s*\(?\s*(?:platform\s*\(\s*)?libs\.([\w.]+)", code):
            ref = m.group(1).lower()
            if ref.startswith("bundles."):
                for lib in cat["bundles"].get(ref[8:], []):
                    if lib in cat["libraries"]:
                        yield *cat["libraries"][lib], i, test
            elif ref in cat["libraries"]:
                yield *cat["libraries"][ref], i, test
        elif m := re.search(_GRADLE_CONF + r"\s*\(?\s*(compose\.[\w.]+)", code):
            yield m.group(1), "", i, test  # Compose Multiplatform accessors: compose.material3 …
        elif m := re.search(r"alias\s*\(\s*libs\.plugins\.([\w.]+)", code):
            if p := cat["plugins"].get(m.group(1).lower()):
                yield *p, i, False
        elif m := re.search(r"""^\s*id\s*\(?\s*['"]([\w.-]+)['"]\s*\)?(?:\s*version\s*\(?\s*['"]([^'"]+)['"])?""", code):
            yield m.group(1), m.group(2) or "", i, False
        elif m := re.search(r"""^\s*kotlin\s*\(\s*['"]([\w.-]+)['"]\s*\)""", code):
            yield f"org.jetbrains.kotlin.{m.group(1)}", "", i, False


def _csproj(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        m = re.search(r'<PackageReference\s+Include="([^"]+)"(?:\s+Version="([^"]+)")?', ln)
        if m:
            yield m.group(1), m.group(2) or "", i, False
        m = re.search(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", ln)
        if m:
            yield "@runtime/dotnet", m.group(1), i, False


def _parser(name: str):
    if name == "package.json":
        return _package_json
    if name.startswith("requirements") and name.endswith(".txt"):
        return _requirements
    if name.endswith(".csproj"):
        return _csproj
    return {"pyproject.toml": _pyproject, "Pipfile": _pipfile, "go.mod": _go_mod, "Cargo.toml": _cargo,
            "Gemfile": _gemfile, "composer.json": _composer, "pom.xml": _maven, "build.gradle": _gradle,
            "build.gradle.kts": _gradle}.get(name)


_RUNTIMES = {"node": "Node.js", "python": "Python", "go": "Go", "rust": "Rust", "ruby": "Ruby", "php": "PHP",
             "dotnet": ".NET", "npm": "npm", "pnpm": "pnpm", "yarn": "Yarn", "bun": "Bun"}


def _version(v: str) -> str:
    """"==0.115.*" → "0.115.*", "^14.2.5" → "14.2.5"; ranges stay as written; "$var" (Gradle) → ""."""
    v = v.strip()
    if v.startswith("$") or v in ("*", "latest"):
        return ""
    return re.sub(r"^(?:==|=|\^|~(?!=))\s*(?=\d)", "", v)


def _item(pkg: str, version: str, file: str, line: int, dev: bool) -> dict | None:
    if pkg.startswith("@runtime/"):
        key = pkg.split("/", 1)[1]
        cat = "tooling" if key in ("npm", "pnpm", "yarn", "bun") else "runtime"
        return {"name": _RUNTIMES.get(key, key), "package": key, "category": cat, "version": _version(version),
                "dev": False, "cite": _cite(file, line)}
    if pkg.startswith("@types/") or pkg == "react-dom":
        return None  # type stubs and React's renderer say nothing new
    known = classify(pkg) or (classify(pkg.split(":", 1)[1]) if ":" in pkg else None)
    label, cat = known if known else (pkg, "other")
    return {"name": label, "package": pkg, "category": cat, "version": _version(version), "dev": dev,
            "cite": _cite(file, line)}


def _repo_wide(store: RepoStore, files: list[str]) -> list[dict]:
    """Docker, compose, CI and deploy configs: one branch for the whole repo."""
    items: list[dict] = []

    def add(name, cat, file, line, version="", detail=""):
        items.append({"name": name, "package": "", "category": cat, "version": version, "dev": False,
                      "detail": detail, "cite": _cite(file, line)})

    for f in files:
        name = f.rsplit("/", 1)[-1]
        low = name.lower()
        if low == "dockerfile" or low.startswith("dockerfile.") or low.endswith(".dockerfile"):
            lines = store.lines(f)
            n = _find(lines, r"^\s*FROM\s", 0)
            base = lines[n - 1].split()[1] if lines and len(lines[n - 1].split()) > 1 else ""
            add("Docker", "infra", f, n, detail=f"{f} · FROM {base}" if base else f)
        elif re.fullmatch(r"(docker-)?compose(\.[\w-]+)?\.ya?ml", low):
            add("Docker Compose", "infra", f, 1, detail=f)
            for i, ln in enumerate(store.lines(f), 1):
                m = re.match(r"^\s*image:\s*['\"]?([^'\"\s:@]+)(?::([^'\"\s@]+))?", ln)
                if m:
                    img = m.group(1).split("/", 1)[-1] if m.group(1).startswith("docker.io/") else m.group(1)
                    hit = _IMAGES.get(img) or _IMAGES.get(img.rsplit("/", 1)[-1])
                    if hit:
                        add(hit[0], hit[1], f, i, m.group(2) or "", detail=f"{img} in {f}")
        elif f.startswith(".github/workflows/") and low.endswith((".yml", ".yaml")):
            lines = store.lines(f)
            n = _find(lines, r"^name:", 0)
            title = lines[n - 1].split(":", 1)[1].strip().strip("'\"") if lines and lines[n - 1].startswith("name:") else name
            add("GitHub Actions", "ci", f, n, detail=title)
        elif f in (".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile", "azure-pipelines.yml", ".travis.yml",
                   "bitbucket-pipelines.yml"):
            label = {".gitlab-ci.yml": "GitLab CI", ".circleci/config.yml": "CircleCI", "Jenkinsfile": "Jenkins",
                     "azure-pipelines.yml": "Azure Pipelines", ".travis.yml": "Travis CI",
                     "bitbucket-pipelines.yml": "Bitbucket Pipelines"}[f]
            add(label, "ci", f, 1, detail=f)
        elif low in ("vercel.json", "netlify.toml", "fly.toml", "railway.json", "railway.toml", "render.yaml",
                     "procfile", "app.yaml", "serverless.yml", "serverless.yaml", "nginx.conf"):
            label = {"vercel.json": "Vercel", "netlify.toml": "Netlify", "fly.toml": "Fly.io",
                     "railway.json": "Railway", "railway.toml": "Railway", "render.yaml": "Render",
                     "procfile": "Procfile (Heroku-style)", "app.yaml": "Google App Engine",
                     "serverless.yml": "Serverless Framework", "serverless.yaml": "Serverless Framework",
                     "nginx.conf": "nginx"}[low]
            add(label, "infra", f, 1, detail=f)
        elif low.endswith(".tf"):
            add("Terraform", "infra", f, 1, detail=f)
        elif low in ("makefile", "justfile"):
            add("Make" if low == "makefile" else "just", "tooling", f, 1, detail=f)
        elif low == ".pre-commit-config.yaml":
            add("pre-commit", "testing", f, 1, detail=f)
        elif low in (".nvmrc", ".python-version", ".node-version", ".tool-versions"):
            ver = (store.lines(f) or [""])[0].strip()
            add("Node.js" if "node" in low else "Python" if "python" in low else "asdf versions", "runtime",
                f, 1, version=ver if low != ".tool-versions" else "", detail=f)
    return items


def _group(items: list[dict]) -> list[dict]:
    """Items → [{id, label, items}] in CATEGORIES order, de-duplicated by display name."""
    by: dict[str, dict[str, dict]] = {}
    for it in items:
        bucket = by.setdefault(it["category"], {})
        key = it["name"].lower() + ("|" + it.get("detail", "") if it["category"] in ("ci", "infra") else "")
        if key in bucket:
            prev = bucket[key]
            prev["dev"] = prev["dev"] and it["dev"]  # used at runtime somewhere → not dev-only
            if it["package"] and it["package"] not in prev.setdefault("also", []) and it["package"] != prev["package"]:
                prev["also"].append(it["package"])
            continue
        bucket[key] = dict(it)
    labels = dict(CATEGORIES)
    out = []
    for cat in sorted(by, key=lambda c: _ORDER.get(c, 99)):
        rows = sorted(by[cat].values(), key=lambda r: (r["dev"], r["name"].lower()))
        out.append({"id": cat, "label": labels.get(cat, cat), "items": rows})
    return out


def languages(store: RepoStore) -> list[dict]:
    counts: dict[str, int] = {}
    for f in store.files():
        lang = _LANGS.get(os.path.splitext(f)[1].lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    total = sum(counts.values()) or 1
    return [{"name": k, "files": v, "share": round(v / total, 3)}
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def build_stack(store: RepoStore, refresh: bool = False) -> dict:
    cached = store.cache_get("stack")
    if cached and not refresh and cached.get("snapshot") == store.snapshot_hash:
        return cached
    files = sorted(store.files())
    workspaces: dict[str, dict] = {}
    # a Gradle build is one workspace however deep its modules sit: the folder with settings.gradle
    gradle_roots = sorted({f.rsplit("/", 1)[0] if "/" in f else "" for f in files
                           if f.rsplit("/", 1)[-1] in ("settings.gradle", "settings.gradle.kts")},
                          key=len, reverse=True)
    catalogs: dict[str, dict] = {}
    for f in files:
        name = f.rsplit("/", 1)[-1]
        if not _is_manifest(f) or not (parse := _parser(name)):
            continue
        d = f.rsplit("/", 1)[0] if "/" in f else ""
        if name.startswith("build.gradle"):
            d = next((r for r in gradle_roots if r == "" or d == r or d.startswith(r + "/")), d)
            if d not in catalogs:
                toml = f"{d}/gradle/libs.versions.toml" if d else "gradle/libs.versions.toml"
                try:
                    catalogs[d] = version_catalog(store.lines(toml)) if toml in files else {}
                except Exception as e:  # noqa: BLE001
                    log.warning("stack: could not parse %s (%s)", toml, e)
                    catalogs[d] = {}
            parse = (lambda lines, c=catalogs[d] or None: _gradle(lines, c))
        ws = workspaces.setdefault(d, {"path": d, "manifests": [], "items": []})
        ws["manifests"].append(f)
        try:
            for pkg, ver, line, dev in parse(store.lines(f)):
                if it := _item(pkg, ver, f, line, dev):
                    ws["items"].append(it)
        except Exception as e:  # noqa: BLE001 — one odd manifest must not hide the rest of the stack
            log.warning("stack: could not parse %s (%s)", f, e)

    groups = []
    for d in sorted(workspaces, key=lambda p: (p != "", p)):
        ws = workspaces[d]
        if not ws["items"]:
            continue
        cats = _group(ws["items"])
        groups.append({"path": d, "name": d or "(repo root)", "manifests": ws["manifests"], "categories": cats,
                       "count": sum(len(c["items"]) for c in cats)})
    wide = _repo_wide(store, files)
    if wide:
        cats = _group(wide)
        groups.append({"path": "*", "name": "Infrastructure & delivery", "manifests": [], "categories": cats,
                       "count": sum(len(c["items"]) for c in cats)})

    known = {(it["name"], it["category"]) for g in groups for c in g["categories"] if c["id"] != "other"
             for it in c["items"]}
    result = {
        "repo": store.meta.get("name") or store.repo_id,
        "languages": languages(store),
        "groups": groups,
        "technologies": len(known),
        "snapshot": store.snapshot_hash,
    }
    store.cache_put("stack", result)
    log.info("stack: repo=%s workspaces=%d technologies=%d", store.repo_id, len(groups), len(known))
    return result
