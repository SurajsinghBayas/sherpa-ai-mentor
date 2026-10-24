"""Tech stack: what a repo is built with, read from its own manifests.

Each directory with a manifest (package.json, requirements.txt, pyproject.toml, go.mod, Cargo.toml,
Gemfile, composer.json, pom.xml, build.gradle, *.csproj, pubspec.yaml, Package.swift, Podfile,
CMakeLists.txt, vcpkg.json, conanfile, mix.exs, build.sbt, R DESCRIPTION, Julia Project.toml …) is a
workspace, and multi-module builds are one workspace however deep their modules sit: Gradle (settings.gradle,
with libs.* aliases read from gradle/libs.versions.toml), Maven (<modules>), CMake and Xcode projects.
Dependencies are sorted into categories (frameworks, databases, AI, testing …). Dockerfiles, compose files, CI
workflows and deploy configs form one more branch for the whole repo. Every entry cites the line
that declares it, so the tree can be checked like any answer. No language model is used, so the
stack is free and quick to build.
"""
import functools
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
# Dart, Swift/iOS, C/C++, Elixir, Scala, R, Julia, .NET: keys carry the registry prefix (pub:, swift:, pod:,
# cpp:, hex:, cran:, jl:) or are Maven/NuGet coordinates, so they can't shadow an npm or PyPI name
_KNOWN_MORE = {
    "framework": {
        "warp": "warp", "poem": "Poem", "leptos": "Leptos", "yew": "Yew", "dioxus": "Dioxus", "bevy": "Bevy",
        "github.com/urfave/cli*": "urfave/cli", "github.com/gin-contrib/*": "Gin middleware",
        "github.com/quic-go/quic-go": "QUIC", "golang.org/x/net": "x/net", "minimalapi.endpoint": "Minimal API endpoints",
        "pub:flutter": "Flutter", "swift:vapor": "Vapor", "swift:swift-composable-architecture": "Composable Architecture",
        "hex:phoenix": "Phoenix", "hex:phoenix_live_view": "Phoenix LiveView", "hex:plug_cowboy": "Plug + Cowboy",
        "hex:plug": "Plug", "com.typesafe.play:*": "Play Framework", "org.playframework:*": "Play Framework",
        "com.typesafe.akka:*": "Akka", "org.apache.pekko:*": "Pekko", "org.http4s:*": "http4s", "dev.zio:zio-http*": "ZIO HTTP",
        "com.softwaremill.sttp.tapir:*": "Tapir", "cran:shiny": "Shiny", "cran:plumber": "plumber", "jl:genie": "Genie",
        "cpp:qt5": "Qt", "cpp:qt6": "Qt", "cpp:qt": "Qt", "cpp:drogon": "Drogon", "cpp:crow": "Crow",
        "microsoft.aspnetcore*": "ASP.NET Core", "microsoft.maui*": "MAUI", "avalonia*": "Avalonia",
        "org.springframework*": "Spring", "org.springframework.boot*": "Spring Boot", "io.vertx:*": "Vert.x",
        "jakarta.*": "Jakarta EE", "io.dropwizard*": "Dropwizard",
    },
    "ui": {
        "pub:cupertino_icons": "Cupertino icons", "pub:google_fonts": "Google Fonts", "pub:flutter_svg": "flutter_svg",
        "pub:cached_network_image": "cached_network_image", "pub:go_router": "go_router", "pub:auto_route": "auto_route",
        "swift:kingfisher": "Kingfisher", "pod:kingfisher": "Kingfisher", "swift:snapkit": "SnapKit", "pod:snapkit": "SnapKit",
        "swift:lottie-ios": "Lottie", "swift:lottie-spm": "Lottie", "pod:lottie-ios": "Lottie", "pod:sdwebimage": "SDWebImage",
        "swift:sdwebimage": "SDWebImage", "cpp:imgui": "Dear ImGui", "cpp:sdl2": "SDL", "cpp:sdl3": "SDL", "cpp:glfw": "GLFW",
        "cpp:glfw3": "GLFW", "cpp:opengl": "OpenGL", "cpp:vulkan": "Vulkan", "cpp:sfml": "SFML", "cran:ggplot2": "ggplot2",
        "cran:plotly": "plotly", "jl:plots": "Plots.jl", "jl:makie": "Makie", "mudblazor": "MudBlazor",
    },
    "data": {
        "anyhow": "anyhow", "thiserror": "thiserror", "serde_*": "Serde", "regex": "regex", "regex-*": "regex",
        "rayon": "Rayon", "crossbeam*": "crossbeam", "chrono": "chrono", "uuid": "uuid", "hyper": "hyper",
        "github.com/go-playground/validator*": "validator", "google.golang.org/protobuf": "Protocol Buffers",
        "github.com/golang/protobuf": "Protocol Buffers", "github.com/bytedance/sonic": "Sonic (JSON)",
        "github.com/json-iterator/go": "json-iterator", "github.com/goccy/go-json": "go-json",
        "github.com/google/uuid": "uuid", "github.com/samber/lo": "lo", "ardalis.*": "Ardalis libraries",
        "system.text.json": "System.Text.Json", "blazored.*": "Blazored",
        "pub:provider": "Provider", "pub:flutter_riverpod": "Riverpod", "pub:riverpod": "Riverpod",
        "pub:hooks_riverpod": "Riverpod", "pub:flutter_bloc": "BLoC", "pub:bloc": "BLoC", "pub:get": "GetX",
        "pub:mobx": "MobX", "pub:dio": "Dio", "pub:http": "http", "pub:json_serializable": "json_serializable",
        "pub:freezed": "Freezed", "pub:freezed_annotation": "Freezed", "pub:get_it": "get_it", "pub:shared_preferences": "shared_preferences",
        "swift:alamofire": "Alamofire", "pod:alamofire": "Alamofire", "swift:rxswift": "RxSwift", "pod:rxswift": "RxSwift",
        "swift:swift-collections": "Swift Collections", "swift:swift-algorithms": "Swift Algorithms", "swift:moya": "Moya",
        "pod:moya": "Moya", "swift:swiftyjson": "SwiftyJSON", "pod:swiftyjson": "SwiftyJSON",
        "cpp:boost": "Boost", "cpp:nlohmann_json": "nlohmann/json", "cpp:nlohmann-json": "nlohmann/json", "cpp:fmt": "fmt",
        "cpp:spdlog": "spdlog", "cpp:eigen3": "Eigen", "cpp:eigen": "Eigen", "cpp:protobuf": "Protocol Buffers",
        "cpp:grpc": "gRPC", "cpp:curl": "libcurl", "cpp:abseil": "Abseil", "cpp:absl": "Abseil", "cpp:zlib": "zlib",
        "cpp:rapidjson": "RapidJSON", "cpp:yaml-cpp": "yaml-cpp", "cpp:asio": "Asio", "cpp:threads": "Threads",
        "hex:jason": "Jason", "hex:ecto": "Ecto", "hex:absinthe": "Absinthe", "hex:oban": "Oban", "hex:broadway": "Broadway",
        "hex:tesla": "Tesla", "hex:req": "Req", "hex:finch": "Finch", "hex:httpoison": "HTTPoison",
        "org.typelevel:cats*": "Cats", "dev.zio:*": "ZIO", "io.circe:*": "Circe", "co.fs2:*": "fs2",
        "cran:dplyr": "dplyr", "cran:tidyr": "tidyr", "cran:data.table": "data.table", "cran:tidyverse": "tidyverse",
        "cran:readr": "readr", "cran:purrr": "purrr", "cran:httr": "httr", "cran:httr2": "httr2", "cran:jsonlite": "jsonlite",
        "cran:rcpp": "Rcpp", "jl:dataframes": "DataFrames.jl", "jl:csv": "CSV.jl", "jl:json": "JSON.jl", "jl:json3": "JSON3.jl",
        "newtonsoft.json": "Json.NET", "automapper*": "AutoMapper", "mediatr*": "MediatR", "fluentvalidation*": "FluentValidation",
        "polly*": "Polly", "serilog*": "Serilog", "com.fasterxml.jackson*": "Jackson", "com.google.guava:*": "Guava",
        "org.projectlombok:*": "Lombok", "org.mapstruct:*": "MapStruct", "org.slf4j:*": "SLF4J", "ch.qos.logback:*": "Logback",
        "org.apache.kafka:*": "Kafka client", "org.springframework.kafka:*": "Spring Kafka",
    },
    "database": {
        "sea-orm": "SeaORM", "rusqlite": "SQLite (rusqlite)", "redis": "Redis", "mongodb": "MongoDB",
        "go.mongodb.org/mongo-driver*": "MongoDB", "github.com/jmoiron/sqlx": "sqlx", "github.com/lib/pq": "PostgreSQL (pq)",
        "github.com/go-sql-driver/mysql": "MySQL", "github.com/mattn/go-sqlite3": "SQLite", "entgo.io/ent": "ent",
        "pub:sqflite": "sqflite", "pub:drift": "Drift", "pub:hive": "Hive", "pub:hive_flutter": "Hive", "pub:isar": "Isar",
        "pub:cloud_firestore": "Cloud Firestore", "pub:supabase_flutter": "Supabase", "swift:realm-swift": "Realm",
        "pod:realmswift": "Realm", "swift:grdb.swift": "GRDB", "swift:sqlite.swift": "SQLite.swift", "pod:sqlite.swift": "SQLite.swift",
        "swift:fluent": "Fluent", "cpp:sqlite3": "SQLite", "cpp:unofficial-sqlite3": "SQLite", "cpp:postgresql": "PostgreSQL",
        "cpp:libpqxx": "libpqxx", "cpp:hiredis": "Redis (hiredis)", "cpp:mongocxx": "MongoDB", "hex:ecto_sql": "Ecto SQL",
        "hex:postgrex": "PostgreSQL (Postgrex)", "hex:myxql": "MySQL", "hex:redix": "Redis", "org.tpolecat:doobie*": "Doobie",
        "com.typesafe.slick:*": "Slick", "cran:dbi": "DBI", "cran:rpostgres": "PostgreSQL", "cran:rsqlite": "SQLite",
        "microsoft.entityframeworkcore*": "Entity Framework Core", "dapper": "Dapper", "npgsql*": "PostgreSQL (Npgsql)",
        "stackexchange.redis": "Redis", "mongodb.driver": "MongoDB", "org.postgresql:*": "PostgreSQL", "com.mysql:*": "MySQL",
        "mysql:mysql-connector-java": "MySQL", "org.hibernate*": "Hibernate", "org.mybatis*": "MyBatis", "org.flywaydb:*": "Flyway",
        "org.liquibase:*": "Liquibase", "com.h2database:*": "H2", "redis.clients:*": "Redis (Jedis)", "org.mongodb:*": "MongoDB",
    },
    "auth": {
        "jsonwebtoken": "jsonwebtoken", "github.com/golang-jwt/jwt*": "golang-jwt", "golang.org/x/crypto": "x/crypto",
        "system.identitymodel.tokens.jwt": "JWT", "pub:firebase_auth": "Firebase Auth", "pub:google_sign_in": "Google Sign-In", "swift:googlesignin-ios": "Google Sign-In",
        "pod:googlesignin": "Google Sign-In", "swift:auth0.swift": "Auth0", "cpp:openssl": "OpenSSL", "hex:guardian": "Guardian",
        "hex:pow": "Pow", "hex:bcrypt_elixir": "bcrypt", "microsoft.identity*": "Microsoft Identity",
        "microsoft.aspnetcore.authentication*": "ASP.NET Core auth", "io.jsonwebtoken:*": "JJWT", "com.auth0:*": "Auth0",
        "org.keycloak:*": "Keycloak",
    },
    "ai": {
        "pub:google_generative_ai": "Gemini SDK", "pub:firebase_vertexai": "Vertex AI", "pub:tflite_flutter": "TensorFlow Lite",
        "swift:openai": "OpenAI (Swift)", "swift:mlx-swift": "MLX", "cpp:torch": "LibTorch", "cpp:opencv": "OpenCV",
        "cpp:opencv4": "OpenCV", "cpp:onnxruntime": "ONNX Runtime", "cpp:cuda": "CUDA", "cpp:cudatoolkit": "CUDA",
        "cpp:llama": "llama.cpp", "hex:nx": "Nx", "hex:axon": "Axon", "hex:bumblebee": "Bumblebee",
        "org.apache.spark:*": "Apache Spark", "cran:caret": "caret", "cran:tidymodels": "tidymodels", "cran:xgboost": "XGBoost",
        "jl:flux": "Flux.jl", "jl:mlj": "MLJ", "microsoft.ml*": "ML.NET", "microsoft.semantickernel*": "Semantic Kernel",
        "dev.langchain4j:*": "LangChain4j", "org.springframework.ai:*": "Spring AI", "com.openai:*": "OpenAI (Java)",
    },
    "testing": {
        "criterion": "Criterion", "proptest": "proptest", "quickcheck": "QuickCheck", "insta": "insta",
        "mockall": "mockall", "libfuzzer-sys": "cargo-fuzz", "arbitrary": "arbitrary", "go.uber.org/mock": "gomock",
        "github.com/golang/mock": "gomock", "github.com/onsi/ginkgo*": "Ginkgo", "github.com/onsi/gomega": "Gomega",
        "nsubstitute*": "NSubstitute", "bogus": "Bogus", "pod:cocoapods": "CocoaPods",
        "pub:flutter_test": "Flutter test", "pub:test": "Dart test", "pub:mockito": "Mockito (Dart)", "pub:mocktail": "Mocktail",
        "pub:bloc_test": "bloc_test", "pub:integration_test": "integration_test", "pub:flutter_lints": "Flutter lints",
        "pub:lints": "Dart lints", "pub:very_good_analysis": "Very Good Analysis", "swift:quick": "Quick", "swift:nimble": "Nimble",
        "pod:quick": "Quick", "pod:nimble": "Nimble", "swift:swift-snapshot-testing": "Snapshot testing", "swift:swiftlint": "SwiftLint",
        "pod:swiftlint": "SwiftLint", "cpp:gtest": "GoogleTest", "cpp:googletest": "GoogleTest", "cpp:catch2": "Catch2",
        "cpp:doctest": "doctest", "cpp:benchmark": "Google Benchmark", "cpp:ctest": "CTest", "hex:credo": "Credo",
        "hex:dialyxir": "Dialyxir", "hex:ex_machina": "ExMachina", "hex:mox": "Mox", "hex:excoveralls": "ExCoveralls",
        "org.scalatest:*": "ScalaTest", "org.scalameta:munit*": "MUnit", "org.specs2:*": "specs2", "org.scalacheck:*": "ScalaCheck",
        "cran:testthat": "testthat", "cran:knitr": "knitr", "cran:rmarkdown": "R Markdown", "cran:covr": "covr",
        "jl:test": "Test (Julia)", "xunit*": "xUnit", "nunit*": "NUnit", "mstest*": "MSTest", "moq": "Moq",
        "fluentassertions": "FluentAssertions", "microsoft.net.test.sdk": ".NET test SDK", "coverlet*": "coverlet",
        "org.junit*": "JUnit", "junit:junit": "JUnit", "org.mockito:*": "Mockito", "org.assertj:*": "AssertJ",
        "org.testcontainers:*": "Testcontainers", "io.rest-assured:*": "REST Assured", "org.jacoco:*": "JaCoCo",
        "org.springframework.boot:spring-boot-starter-test": "Spring Boot test",
    },
    "tooling": {
        "cocoapods": "CocoaPods", "fastlane": "fastlane", "jazzy": "Jazzy", "xcpretty": "xcpretty",
        "swashbuckle*": "Swagger (Swashbuckle)", "nswag*": "NSwag", "microsoft.visualstudio*": "Visual Studio tooling",
        "microsoft.web.librarymanager*": "LibMan", "buildbundlerminifier": "Bundler & Minifier",
        "github.com/spf13/viper": "Viper", "github.com/joho/godotenv": "godotenv",
        "pub:build_runner": "build_runner", "pub:flutter_launcher_icons": "flutter_launcher_icons",
        "pub:flutter_native_splash": "flutter_native_splash", "pub:intl": "intl", "pub:flutter_localizations": "Flutter l10n",
        "swift:swift-argument-parser": "Swift Argument Parser", "swift:swift-format": "swift-format",
        "swift:swift-log": "SwiftLog", "pod:firebase/crashlytics": "Crashlytics", "hex:ex_doc": "ExDoc", "hex:esbuild": "esbuild",
        "hex:tailwind": "Tailwind CSS", "hex:telemetry": "Telemetry", "cran:devtools": "devtools", "cran:roxygen2": "roxygen2",
        "cran:usethis": "usethis", "org.scalameta:sbt-scalafmt": "scalafmt", "com.github.sbt:sbt-native-packager": "sbt-native-packager",
        "org.springframework.boot:spring-boot-maven-plugin": "Spring Boot Maven plugin",
        "org.springframework.boot:spring-boot-devtools": "Spring Boot DevTools",
    },
    "infra": {
        "tracing": "tracing", "tracing-*": "tracing", "log": "log", "env_logger": "env_logger",
        "go.uber.org/zap": "zap", "github.com/sirupsen/logrus": "Logrus", "github.com/rs/zerolog": "zerolog",
        "github.com/prometheus/client_golang": "Prometheus", "go.opentelemetry.io/*": "OpenTelemetry",
        "pub:firebase_core": "Firebase", "pub:firebase_*": "Firebase", "pub:supabase": "Supabase", "swift:firebase-ios-sdk": "Firebase",
        "pod:firebase*": "Firebase", "awssdk*": "AWS SDK", "software.amazon.awssdk:*": "AWS SDK", "com.amazonaws:*": "AWS SDK",
        "azure.*": "Azure SDK", "com.azure:*": "Azure SDK", "com.google.cloud:*": "Google Cloud", "io.micrometer:*": "Micrometer",
        "io.opentelemetry*": "OpenTelemetry", "opentelemetry*": "OpenTelemetry", "hex:sentry": "Sentry", "pub:sentry_flutter": "Sentry",
        "swift:sentry-cocoa": "Sentry", "pod:sentry": "Sentry", "sentry*": "Sentry", "io.sentry:*": "Sentry",
        "org.springframework.cloud:*": "Spring Cloud",
    },
}
_EXACT: dict[str, tuple[str, str]] = {}
_PREFIX: list[tuple[str, str, str]] = []
for _cat, _names in [*_KNOWN_GRADLE.items(), *_KNOWN_MORE.items(), *_KNOWN.items()]:
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
    ".cxx": "C++", ".hh": "C++", ".hxx": "C++", ".cu": "CUDA", ".m": "Objective-C", ".mm": "Objective-C++",
    ".fs": "F#", ".vb": "Visual Basic", ".hs": "Haskell", ".jl": "Julia", ".zig": "Zig", ".clj": "Clojure",
    ".erl": "Erlang", ".groovy": "Groovy", ".pl": "Perl", ".ps1": "PowerShell", ".sc": "Scala", ".sbt": "Scala",
}



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
    return _parser(name) is not None


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
            indirect = "indirect" in ln
            if len(parts) >= 2 and (not indirect or classify(parts[0])):  # unknown transitive modules are noise
                yield parts[0], parts[1], i, indirect


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


def _pom_properties(lines: list[str]) -> dict:
    pm = re.search(r"<properties>(.*?)</properties>", "\n".join(lines), re.S)
    return dict(re.findall(r"<([\w.-]+)>([^<]*)</\1>", pm.group(1))) if pm else {}


def _maven(lines: list[str], inherited: dict | None = None):
    """<dependency>/<parent>/<plugin> blocks as group:artifact with ${property} versions resolved;
    a module also sees the properties of its build's root pom."""
    text = "\n".join(lines)
    props = {**(inherited or {}), **_pom_properties(lines)}

    def resolve(v: str) -> str:
        return re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), ""), v or "")

    for key in ("java.version", "maven.compiler.release", "maven.compiler.source"):
        if key in props:
            yield "@runtime/java", props[key], _find(lines, rf"<{re.escape(key)}>"), False
            break
    for m in re.finditer(r"<(dependency|parent|plugin)>(.*?)</\1>", text, re.S):
        kind, body = m.group(1), m.group(2)
        tag = lambda t: (re.search(rf"<{t}>([^<]+)</{t}>", body) or [None, ""])[1].strip()  # noqa: E731
        art = tag("artifactId")
        if not art:
            continue
        pkg = f'{tag("groupId") or "org.apache.maven.plugins"}:{art}'
        if kind == "plugin" and not (classify(pkg) or classify(art)):
            continue  # compiler/surefire/jar plugins say nothing about the stack
        line = text.count("\n", 0, m.start() + body.find("<artifactId>")) + 1
        yield pkg, resolve(tag("version")), line, tag("scope") in ("test", "provided") and kind == "dependency"


def _dotnet(lines: list[str]):
    """.csproj/.fsproj/.vbproj, Directory.Packages.props and packages.config."""
    for i, ln in enumerate(lines, 1):
        m = re.search(r'<Package(?:Reference|Version)\s+(?:Include|Update)="([^"]+)"(?:[^>]*?\sVersion="([^"]+)")?', ln)
        if m:
            yield m.group(1), m.group(2) or "", i, "test" in m.group(1).lower()
        m = re.search(r'<package\s+id="([^"]+)"(?:\s+version="([^"]+)")?', ln)
        if m:
            yield m.group(1), m.group(2) or "", i, False
        m = re.search(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", ln)
        if m:
            yield "@runtime/dotnet", m.group(1), i, False
        m = re.search(r'<Project\s+Sdk="Microsoft\.NET\.Sdk\.(Web|Razor|BlazorWebAssembly|Worker)"', ln)
        if m:
            yield "Microsoft.AspNetCore", "", i, False


def _global_json(lines: list[str]):
    try:
        ver = json.loads("\n".join(lines)).get("sdk", {}).get("version")
    except (ValueError, AttributeError):
        return
    if ver:
        yield "@runtime/dotnet", f"SDK {ver}", _find(lines, r'"version"'), False


def _yaml_blocks(lines: list[str]):
    """(top-level key, child key, value, line) for a simple two-level YAML file."""
    top, child_indent = "", None
    for i, ln in enumerate(lines, 1):
        body = ln.split(" #", 1)[0].rstrip()
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        indent = len(body) - len(body.lstrip())
        if indent == 0:
            top, child_indent = body.split(":", 1)[0].strip(), None
            continue
        if child_indent is None:
            child_indent = indent
        if indent == child_indent and ":" in body:
            k, v = body.strip().split(":", 1)
            yield top, k.strip().strip("'\""), v.strip().strip("'\""), i


def _pubspec(lines: list[str]):
    for top, name, val, i in _yaml_blocks(lines):
        if top == "environment":
            if name == "sdk":
                yield "@runtime/dart", val, i, False
            elif name == "flutter":
                yield "pub:flutter", val, i, False
        elif top in ("dependencies", "dev_dependencies"):
            yield f"pub:{name}", val, i, top == "dev_dependencies"


def _swift_package(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        if m := re.match(r"//\s*swift-tools-version\s*:\s*([\d.]+)", ln.strip()):
            yield "@runtime/swift", m.group(1), i, False
        m = re.search(r'\.package\(\s*(?:name:\s*"[^"]*",\s*)?url:\s*"([^"]+)"\s*,\s*(?:from:|exact:|\.upToNextMajor\(from:|\.upToNextMinor\(from:)?\s*"?([\d.]*)', ln)
        if m:
            yield "swift:" + m.group(1).rstrip("/").rsplit("/", 1)[-1].removesuffix(".git"), m.group(2), i, False


def _package_resolved(lines: list[str]):
    try:
        data = json.loads("\n".join(lines))
    except ValueError:
        return
    pins = data.get("pins") or data.get("object", {}).get("pins") or []
    for p in pins:
        url = p.get("location") or p.get("repositoryURL") or ""
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git") or p.get("identity") or p.get("package", "")
        ver = (p.get("state") or {}).get("version") or ""
        yield "swift:" + name, ver, _find(lines, re.escape(url) if url else re.escape(name)), False


def _pbxproj(lines: list[str]):
    """Swift packages added in Xcode (no Package.swift): XCRemoteSwiftPackageReference entries."""
    url = None
    for i, ln in enumerate(lines, 1):
        if m := re.search(r'repositoryURL\s*=\s*"([^"]+)"', ln):
            url = (m.group(1), i)
        elif url and (m := re.search(r"(?:minimumVersion|version)\s*=\s*([\d.]+)", ln)):
            yield "swift:" + url[0].rstrip("/").rsplit("/", 1)[-1].removesuffix(".git"), m.group(1), url[1], False
            url = None
        if m := re.search(r"SWIFT_VERSION\s*=\s*([\d.]+)", ln):
            yield "@runtime/swift", m.group(1), i, False


def _podfile(lines: list[str]):
    target_test = False
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if m := re.match(r"target\s+['\"]([^'\"]+)['\"]", s):
            target_test = "test" in m.group(1).lower()
        if m := re.match(r"""pod\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?""", s):
            yield "pod:" + m.group(1), m.group(2) or "", i, target_test
        elif m := re.match(r"""platform\s+:(\w+)\s*,\s*['"]([^'"]+)['"]""", s):
            yield "@runtime/" + m.group(1), m.group(2), i, False


def _cmake(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        s = ln.split("#", 1)[0]
        if m := re.search(r"cmake_minimum_required\s*\(\s*VERSION\s+([\d.]+)", s, re.I):
            yield "@runtime/cmake", m.group(1), i, False
        if re.search(r"\bproject\s*\(", s, re.I):
            call = " ".join(lines[i - 1:i + 5]).split(")", 1)[0]
            if "LANGUAGES" in call:
                for lang in re.findall(r"\b(CXX|C|CUDA|Fortran|Swift|OBJC)\b", call.split("LANGUAGES", 1)[1]):
                    yield "@runtime/" + {"CXX": "cpp", "C": "c"}.get(lang, lang.lower()), "", i, False
        if m := re.search(r"set\s*\(\s*CMAKE_(CXX|C)_STANDARD\s+(\d+)", s, re.I):
            lang = m.group(1).upper()
            yield ("@runtime/cpp" if lang == "CXX" else "@runtime/c"), ("C++" if lang == "CXX" else "C") + m.group(2), i, False
        if m := re.search(r"find_package\s*\(\s*([\w:+-]+)(?:\s+([\d.]+))?", s, re.I):
            yield "cpp:" + m.group(1), m.group(2) or "", i, False
        if m := re.search(r"FetchContent_Declare\s*\(\s*([\w-]+)", s, re.I):
            yield "cpp:" + m.group(1), "", i, False
        if m := re.search(r"""CPMAddPackage\s*\(\s*"?(?:gh:[\w.-]+/)?([\w.-]+)(?:#|@)?([\w.]*)""", s, re.I):
            if m.group(1).upper() != "NAME":
                yield "cpp:" + m.group(1), m.group(2), i, False
        if m := re.search(r"enable_testing\s*\(", s, re.I):
            yield "cpp:CTest", "", i, True


def _vcpkg(lines: list[str]):
    try:
        deps = json.loads("\n".join(lines)).get("dependencies", [])
    except (ValueError, AttributeError):
        return
    for d in deps:
        name = d if isinstance(d, str) else d.get("name", "")
        if name:
            yield "cpp:" + name, (d.get("version>=", "") if isinstance(d, dict) else ""), _find(lines, rf'"{re.escape(name)}"'), False


def _conan(lines: list[str]):
    section = ""
    for i, ln in enumerate(lines, 1):
        s = ln.split("#", 1)[0].strip()
        if m := re.match(r"\[(\w+)\]", s):
            section = m.group(1)
            continue
        dev = "tool" in section or "test" in section or "build" in section
        for m in re.finditer(r"""([A-Za-z][\w.+-]*)/\[?([\w.<>=~ ,^-]+?)\]?(?:@[\w/.-]+)?(?=["'\s,)]|$)""", s):
            if section in ("requires", "tool_requires", "build_requires", "test_requires") or "requires" in s:
                yield "cpp:" + m.group(1), m.group(2).strip(), i, dev or "tool_requires" in s or "test_requires" in s


def _mix(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        if m := re.search(r'elixir:\s*"([^"]+)"', ln):
            yield "@runtime/elixir", m.group(1), i, False
        if m := re.search(r'\{\s*:(\w+)\s*,\s*"([^"]+)"([^}]*)\}', ln):
            opts = m.group(3)
            only = re.search(r"only:\s*(\[[^\]]*\]|:\w+)", opts)
            yield "hex:" + m.group(1), m.group(2), i, bool(only and ":prod" not in only.group(1))
        elif m := re.search(r"\{\s*:(\w+)\s*,\s*(?:github|git|path):", ln):
            yield "hex:" + m.group(1), "", i, False


def _sbt(lines: list[str]):
    for i, ln in enumerate(lines, 1):
        s = ln.split("//", 1)[0]
        if m := re.search(r'scalaVersion\s*:=\s*"([^"]+)"', s):
            yield "@runtime/scala", m.group(1), i, False
        for m in re.finditer(r'"([\w.-]+)"\s*%%?%?\s*"([\w.-]+)"\s*%\s*"([^"]+)"(\s*%\s*"?(\w+)"?)?', s):
            yield f"{m.group(1)}:{m.group(2)}", m.group(3), i, bool(m.group(5) and m.group(5).lower() in ("test", "it"))
        if m := re.search(r'addSbtPlugin\(\s*"([\w.-]+)"\s*%\s*"([\w.-]+)"\s*%\s*"([^"]+)"', s):
            yield f"{m.group(1)}:{m.group(2)}", m.group(3), i, True


def _setup_py(lines: list[str]):
    text = "\n".join(lines)
    for key, dev in (("install_requires", False), ("tests_require", True), ("extras_require", True)):
        m = re.search(key + r"\s*=\s*([\[{])", text)
        if not m:
            continue
        depth, end = 0, m.start(1)
        for end in range(m.start(1), len(text)):
            depth += {"[": 1, "{": 1, "]": -1, "}": -1}.get(text[end], 0)
            if depth == 0:
                break
        first = text.count("\n", 0, m.start(1))
        for i in range(first, text.count("\n", 0, end) + 1):
            for q in re.findall(r"[\"']([A-Za-z0-9][^\"']*)[\"']", lines[i]):
                if ":" not in q and (r := _REQ.match(q)):
                    yield r.group(1), r.group(2).strip(), i + 1, dev
    if m := re.search(r"python_requires\s*=\s*[\"']([^\"']+)", text):
        yield "@runtime/python", m.group(1), _find(lines, r"python_requires"), False


def _setup_cfg(lines: list[str]):
    section, key = "", ""
    for i, ln in enumerate(lines, 1):
        s = ln.split("#", 1)[0].rstrip()
        if m := re.match(r"\[([^\]]+)\]", s.strip()):
            section, key = m.group(1), ""
            continue
        if m := re.match(r"(\w[\w-]*)\s*=\s*(.*)$", s):
            key, s = m.group(1), m.group(2)
            if key == "python_requires":
                yield "@runtime/python", s.strip(), i, False
                continue
        if section.startswith("options") and key in ("install_requires", "tests_require") or section == "options.extras_require":
            if (m := _REQ.match(s.strip())) and s.strip():
                yield m.group(1), m.group(2).strip(), i, key != "install_requires"


def _conda(lines: list[str]):
    in_deps = False
    for i, ln in enumerate(lines, 1):
        if re.match(r"^dependencies\s*:", ln):
            in_deps = True
            continue
        if in_deps and re.match(r"^\S", ln):
            in_deps = False
        m = re.match(r"^\s*-\s*([A-Za-z0-9_.-]+)\s*(?:[=<>!]=?\s*([\w.*]+))?\s*$", ln) if in_deps else None
        if m and m.group(1) != "pip":
            name = m.group(1).split("::")[-1]
            yield ("@runtime/python" if name == "python" else name), m.group(2) or "", i, False


def _r_description(lines: list[str]):
    field = ""
    for i, ln in enumerate(lines, 1):
        if m := re.match(r"^([\w@/.-]+):\s*(.*)$", ln):
            field, rest = m.group(1), m.group(2)
        elif ln[:1].isspace():
            rest = ln
        else:
            continue
        if field not in ("Depends", "Imports", "LinkingTo", "Suggests"):
            continue
        for m in re.finditer(r"([A-Za-z][\w.]*)\s*(?:\(\s*([^)]+)\))?", rest):
            name = m.group(1)
            if name == "R":
                yield "@runtime/r", (m.group(2) or "").strip(), i, False
            else:
                yield "cran:" + name, (m.group(2) or "").strip(), i, field == "Suggests"


def _julia_project(lines: list[str]):
    compat = dict((k, v) for k, v, _, _ in _toml_tables(lines, lambda t: t == "compat"))
    for k, _v, i, _ in _toml_tables(lines, lambda t: t in ("deps", "extras")):
        yield "jl:" + k, compat.get(k, ""), i, False
    if "julia" in compat:
        yield "@runtime/julia", compat["julia"], _find(lines, r"^\s*julia\s*="), False


_BY_NAME = {
    "package.json": "_package_json", "pyproject.toml": "_pyproject", "Pipfile": "_pipfile", "setup.py": "_setup_py",
    "setup.cfg": "_setup_cfg", "environment.yml": "_conda", "environment.yaml": "_conda", "go.mod": "_go_mod",
    "Cargo.toml": "_cargo", "Gemfile": "_gemfile", "composer.json": "_composer", "pom.xml": "_maven",
    "build.gradle": "_gradle", "build.gradle.kts": "_gradle", "Directory.Packages.props": "_dotnet",
    "packages.config": "_dotnet", "global.json": "_global_json", "pubspec.yaml": "_pubspec",
    "Package.swift": "_swift_package", "Package.resolved": "_package_resolved", "project.pbxproj": "_pbxproj",
    "Podfile": "_podfile", "CMakeLists.txt": "_cmake", "vcpkg.json": "_vcpkg", "conanfile.txt": "_conan",
    "conanfile.py": "_conan", "mix.exs": "_mix", "build.sbt": "_sbt", "DESCRIPTION": "_r_description",
    "Project.toml": "_julia_project",
}


def _parser(name: str):
    if name.startswith("requirements") and name.endswith(".txt"):
        return _requirements
    if name.endswith((".csproj", ".fsproj", ".vbproj")):
        return _dotnet
    fn = _BY_NAME.get(name)
    return globals()[fn] if fn else None


_RUNTIMES = {"node": "Node.js", "python": "Python", "go": "Go", "rust": "Rust", "ruby": "Ruby", "php": "PHP",
             "dotnet": ".NET", "npm": "npm", "pnpm": "pnpm", "yarn": "Yarn", "bun": "Bun", "java": "Java",
             "dart": "Dart", "swift": "Swift", "ios": "iOS", "osx": "macOS", "macos": "macOS", "tvos": "tvOS",
             "watchos": "watchOS", "cpp": "C++", "c": "C", "cuda": "CUDA", "fortran": "Fortran", "objc": "Objective-C",
             "cmake": "CMake", "elixir": "Elixir", "scala": "Scala", "r": "R", "julia": "Julia"}
_TOOLS = ("npm", "pnpm", "yarn", "bun", "cmake")
# registries whose names would collide with npm/PyPI ones carry a prefix; it is not shown
_ECOSYSTEMS = ("pub:", "swift:", "pod:", "cpp:", "hex:", "cran:", "jl:")


def _version(v: str) -> str:
    """"==0.115.*" → "0.115.*", "^14.2.5" → "14.2.5"; ranges stay as written; "$var" (Gradle) → ""."""
    v = v.strip()
    if v.startswith("$") or v in ("*", "latest"):
        return ""
    return re.sub(r"^(?:==|=|\^|~(?!=))\s*(?=\d)", "", v)


def _item(pkg: str, version: str, file: str, line: int, dev: bool) -> dict | None:
    if pkg.startswith("@runtime/"):
        key = pkg.split("/", 1)[1]
        cat = "tooling" if key in _TOOLS else "runtime"
        return {"name": _RUNTIMES.get(key, key), "package": key, "category": cat, "version": _version(version),
                "dev": False, "cite": _cite(file, line)}
    if pkg.startswith("@types/") or pkg == "react-dom":
        return None  # type stubs and React's renderer say nothing new
    known = classify(pkg) or (classify(pkg.split(":", 1)[1]) if ":" in pkg else None)
    bare = pkg.split(":", 1)[1] if pkg.startswith(_ECOSYSTEMS) else pkg
    label, cat = known if known else (bare, "other")
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


def _own_name(f: str, lines: list[str]) -> str | None:
    """The name a manifest publishes its own package under, so sibling crates/packages aren't listed as dependencies."""
    name = f.rsplit("/", 1)[-1]
    if name == "Cargo.toml":
        table = ""
        for ln in lines:
            s = ln.split("#", 1)[0].strip()
            if s.startswith("["):
                table = s.strip("[]")
            elif table == "package" and (m := re.match(r'name\s*=\s*"([^"]+)"', s)):
                return m.group(1)
    elif name == "package.json":
        m = re.search(r'^\s*"name"\s*:\s*"([^"]+)"', "\n".join(lines[:15]), re.M)
        return m.group(1) if m else None
    elif name == "pubspec.yaml":
        m = re.search(r"^name:\s*(\S+)", "\n".join(lines), re.M)
        return m.group(1) if m else None
    return None


def _dir(f: str) -> str:
    return f.rsplit("/", 1)[0] if "/" in f else ""


def _build_roots(store: RepoStore, files: list[str]) -> dict[str, list[str]]:
    """Folders that hold a whole multi-module build, so nested modules join one workspace:
    Gradle (settings.gradle), Maven (a pom.xml with <modules>), Cargo ([workspace]), .NET (a solution),
    Go (go.work) and CMake (the top CMakeLists.txt)."""
    gradle, maven, cmake, cargo, dotnet, go = [], [], [], [], [], []
    for f in files:
        name = f.rsplit("/", 1)[-1]
        if name.endswith((".sln", ".slnx")):
            dotnet.append(_dir(f))
        elif name == "go.work":
            go.append(_dir(f))
        elif name == "Cargo.toml" and any(ln.strip() == "[workspace]" for ln in store.lines(f)):
            cargo.append(_dir(f))
        elif name in ("settings.gradle", "settings.gradle.kts"):
            gradle.append(_dir(f))
        elif name == "pom.xml" and any("<modules>" in ln for ln in store.lines(f)):
            maven.append(_dir(f))
        elif name == "CMakeLists.txt":
            cmake.append(_dir(f))
    deepest = lambda dirs: sorted(set(dirs), key=len, reverse=True)  # noqa: E731
    return {"gradle": deepest(gradle), "maven": deepest(maven), "cargo": deepest(cargo), "dotnet": deepest(dotnet),
            "go": deepest(go), "cmake": sorted(set(cmake), key=len)}  # CMake: the outermost project wins


def _workspace_dir(f: str, roots: dict[str, list[str]]) -> str:
    parts = f.split("/")
    # Xcode keeps manifests inside App.xcodeproj/ and App.xcworkspace/: the app is the folder above
    for i, part in enumerate(parts[:-1]):
        if part.endswith((".xcodeproj", ".xcworkspace")):
            return "/".join(parts[:i])
    d, name = _dir(f), parts[-1]
    kind = ("gradle" if name.startswith("build.gradle") else "maven" if name == "pom.xml"
            else "cmake" if name == "CMakeLists.txt" else "cargo" if name == "Cargo.toml" else "go" if name == "go.mod"
            else "dotnet" if name.endswith((".csproj", ".fsproj", ".vbproj")) or name in (
                "Directory.Packages.props", "packages.config", "global.json") else None)
    if kind:
        return next((r for r in roots[kind] if r == "" or d == r or d.startswith(r + "/")), d)
    return d


def build_stack(store: RepoStore, refresh: bool = False) -> dict:
    cached = store.cache_get("stack")
    if cached and not refresh and cached.get("snapshot") == store.snapshot_hash:
        return cached
    files = sorted(store.files())
    workspaces: dict[str, dict] = {}
    roots = _build_roots(store, files)
    catalogs: dict[str, dict] = {}
    for f in files:
        name = f.rsplit("/", 1)[-1]
        if not _is_manifest(f) or not (parse := _parser(name)):
            continue
        d = _workspace_dir(f, roots)
        if name.startswith("build.gradle"):
            if d not in catalogs:
                toml = f"{d}/gradle/libs.versions.toml" if d else "gradle/libs.versions.toml"
                try:
                    catalogs[d] = version_catalog(store.lines(toml)) if toml in files else {}
                except Exception as e:  # noqa: BLE001
                    log.warning("stack: could not parse %s (%s)", toml, e)
                    catalogs[d] = {}
            parse = functools.partial(_gradle, catalog=catalogs[d] or None)
        elif name == "pom.xml" and d in roots["maven"]:
            root_pom = f"{d}/pom.xml" if d else "pom.xml"
            parse = functools.partial(_maven, inherited=_pom_properties(store.lines(root_pom)))
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
        own = {n for m in ws["manifests"] if (n := _own_name(m, store.lines(m)))}
        ws["items"] = [it for it in ws["items"] if it["package"].split(":", 1)[-1] not in own]
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
