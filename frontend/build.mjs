import { build } from "esbuild";
import { copyFileSync } from "fs";
await build({
  entryPoints: ["src/main.jsx"], bundle: true, minify: true, sourcemap: false,
  outfile: "dist/app.js", loader: { ".jsx": "jsx", ".css": "css" }, jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' }, logLevel: "info",
});
copyFileSync("index.html", "dist/index.html");
