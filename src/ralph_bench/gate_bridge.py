"""Evaluator-injected browser bridge for the minimal ``gates/v1`` API."""

from __future__ import annotations


GATES_INIT_SCRIPT = r"""
(() => {
  "use strict";
  const SIDES = new Set(["north", "east", "south", "west"]);
  const state = {
    handlers: null,
    startedAt: null,
    issued: new Map(),
    completions: new Map(),
    invalid: []
  };
  const elapsed = () => state.startedAt === null ? 0 : Math.max(0, Math.round(performance.now() - state.startedAt));
  const invalid = (code, detail, id = null) => {
    state.invalid.push({code, detail: String(detail).slice(0, 500), id, at_ms: elapsed()});
    return false;
  };
  const cleanId = (value) => typeof value === "string" && value.trim() ? value.trim() : null;
  const cleanSide = (value) => typeof value === "string" && SIDES.has(value.toLowerCase()) ? value.toLowerCase() : null;
  const finish = (kind, rawId, rawFinish = null) => {
    const id = cleanId(rawId);
    if (!id) return invalid("invalid-completion-id", "completion ID must be a non-empty string");
    const issued = state.issued.get(id);
    if (!issued) return invalid("unknown-completion", "completion ID was not issued by Ralph", id);
    if (issued.kind !== kind) return invalid("completion-kind-mismatch", `expected ${issued.kind}, received ${kind}`, id);
    if (state.completions.has(id)) return invalid("duplicate-completion", "an ID may finish only once", id);
    let finishGate = null;
    if (kind === "car") {
      finishGate = cleanSide(rawFinish);
      if (!finishGate) return invalid("invalid-finish-gate", "car finish gate must be north, east, south, or west", id);
      if (finishGate !== issued.request.exitsTo) {
        return invalid("wrong-finish-gate", `expected ${issued.request.exitsTo}, received ${finishGate}`, id);
      }
    }
    const completedMs = elapsed();
    state.completions.set(id, {
      kind,
      id,
      finish: finishGate,
      completed_ms: completedMs,
      latency_ms: Math.max(0, completedMs - issued.issued_ms)
    });
    return true;
  };
  const api = {
    apiVersion: "gates/v1",
    register(handlers) {
      if (!handlers || typeof handlers.carArrived !== "function" || typeof handlers.pedestrianArrived !== "function") {
        return invalid("invalid-registration", "register() requires carArrived and pedestrianArrived functions");
      }
      state.handlers = {carArrived: handlers.carArrived, pedestrianArrived: handlers.pedestrianArrived};
      return true;
    },
    carFinished(id, exit) { return finish("car", id, exit); },
    pedestrianFinished(id) { return finish("pedestrian", id); }
  };
  const issue = (kind, request) => {
    if (!state.handlers) throw new Error("gates/v1 callbacks are not registered");
    const id = cleanId(request && request.id);
    if (!id) throw new Error("arrival ID must be a non-empty string");
    if (state.issued.has(id)) throw new Error(`duplicate evaluator arrival ID: ${id}`);
    const publicRequest = Object.freeze({...request});
    state.issued.set(id, {kind, id, request: publicRequest, issued_ms: elapsed()});
    const handler = kind === "car" ? state.handlers.carArrived : state.handlers.pedestrianArrived;
    try {
      const result = handler(publicRequest);
      if (result && typeof result.then === "function") {
        result.catch(error => invalid("arrival-handler-error", error && error.message ? error.message : error, id));
      }
    } catch (error) {
      invalid("arrival-handler-error", error && error.message ? error.message : error, id);
    }
  };
  const counts = () => {
    const issued = [...state.issued.values()];
    const completions = [...state.completions.values()];
    const issuedCars = issued.filter(item => item.kind === "car").length;
    const issuedPedestrians = issued.length - issuedCars;
    const completedCars = completions.filter(item => item.kind === "car").length;
    const completedPedestrians = completions.length - completedCars;
    return {
      api_version: "gates/v1",
      ready: state.handlers !== null,
      time_ms: elapsed(),
      issued_cars: issuedCars,
      completed_cars: completedCars,
      outstanding_cars: issuedCars - completedCars,
      issued_pedestrians: issuedPedestrians,
      completed_pedestrians: completedPedestrians,
      outstanding_pedestrians: issuedPedestrians - completedPedestrians,
      invalid_completions: state.invalid.length
    };
  };
  const driver = {
    apiVersion: "gates/v1",
    ready() { return state.handlers !== null; },
    start() {
      state.issued.clear();
      state.completions.clear();
      state.invalid.length = 0;
      state.startedAt = performance.now();
      return counts();
    },
    addCar(request) { issue("car", request); return counts(); },
    addPedestrian(request) { issue("pedestrian", request); return counts(); },
    snapshot() { return counts(); },
    final() {
      return {
        ...counts(),
        issued: [...state.issued.values()].map(item => ({...item, request: {...item.request}})),
        completions: [...state.completions.values()].map(item => ({...item})),
        invalid: state.invalid.map(item => ({...item}))
      };
    }
  };
  Object.defineProperty(globalThis, "RalphGates", {value: Object.freeze(api), writable: false, configurable: false});
  Object.defineProperty(globalThis, "__RALPH_GATES_DRIVER__", {value: Object.freeze(driver), writable: false, configurable: false});
})();
"""


__all__ = ["GATES_INIT_SCRIPT"]
