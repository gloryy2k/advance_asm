import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";
afterEach(() => cleanup());

// Debounced fetches + a loaded CI machine: give async queries room instead of flaking at the 1s default.
configure({ asyncUtilTimeout: 4000 });
