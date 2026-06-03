// Ambient declaration for Node.js `global` used in jest test files.
// jest runs in Node, so `global` is valid at runtime; this just satisfies tsc.
declare var global: typeof globalThis;
