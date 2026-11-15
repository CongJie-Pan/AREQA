// pdfjs-dist ships no types for its worker bundle; only the handler is used.
declare module 'pdfjs-dist/build/pdf.worker.min.mjs' {
  export const WorkerMessageHandler: unknown;
}
