import * as esbuild from "esbuild";
import { mkdirSync, copyFileSync, existsSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const isWatch = process.argv.includes("--watch");

mkdirSync(join(__dirname, "dist"), { recursive: true });
copyFileSync(join(__dirname, "index.html"), join(__dirname, "dist", "index.html"));
copyFileSync(join(__dirname, "src/styles/app.css"), join(__dirname, "dist", "app.css"));

const ctx = await esbuild.context({
  entryPoints: [join(__dirname, "src/main.tsx")],
  bundle: true,
  outfile: join(__dirname, "dist/app.js"),
  format: "esm",
  target: ["es2020"],
  jsx: "automatic",
  loader: { ".tsx": "tsx", ".ts": "ts", ".css": "empty" },
  define: { "process.env.NODE_ENV": '"production"' },
  minify: !isWatch,
  sourcemap: isWatch,
});

if (isWatch) {
  await ctx.watch();
  console.log("watching…");
} else {
  await ctx.rebuild();
  await ctx.dispose();
  console.log("build done → dist/");
}
