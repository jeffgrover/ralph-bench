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
    invalid: [],
    observations: [],
    invalidObservations: [],
    bodySamples: 0,
    lastObservationMs: null
  };
  const MAX_OBSERVATIONS = 20000;
  const MAX_BODIES = 256;
  const MAX_BODY_SAMPLES = 1000000;
  const OBSERVATION_INTERVAL_MS = 60;
  const elapsed = () => state.startedAt === null ? 0 : Math.max(0, Math.round(performance.now() - state.startedAt));
  const invalid = (code, detail, id = null) => {
    state.invalid.push({code, detail: String(detail).slice(0, 500), id, at_ms: elapsed()});
    return false;
  };
  const cleanId = (value) => typeof value === "string" && value.trim() ? value.trim() : null;
  const cleanSide = (value) => typeof value === "string" && SIDES.has(value.toLowerCase()) ? value.toLowerCase() : null;
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const cleanBody = (raw) => {
    if (!raw || typeof raw !== "object") return null;
    const id = cleanId(raw.id);
    if (!id || !finite(raw.x) || !finite(raw.y) || !finite(raw.length) || !finite(raw.width) || !finite(raw.heading)) return null;
    if (raw.length <= 0 || raw.width <= 0 || raw.length > 1_000 || raw.width > 1_000) return null;
    return {id, x: raw.x, y: raw.y, length: raw.length, width: raw.width, heading: raw.heading};
  };
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
  const observe = (rawBodies) => {
    if (!Array.isArray(rawBodies)) {
      state.invalidObservations.push({code: "invalid-observation", detail: "observe() requires an array", at_ms: elapsed()});
      return false;
    }
    if (rawBodies.length > MAX_BODIES) {
      state.invalidObservations.push({code: "observation-body-limit", detail: `observation contains more than ${MAX_BODIES} bodies`, at_ms: elapsed()});
      return false;
    }
    const bodies = [];
    const seen = new Set();
    for (const raw of rawBodies) {
      const body = cleanBody(raw);
      if (!body) {
        state.invalidObservations.push({code: "invalid-observation-body", detail: "body requires finite id, x, y, length, width, and heading", at_ms: elapsed()});
        return false;
      }
      if (!state.issued.has(body.id)) {
        state.invalidObservations.push({code: "unknown-observation-id", detail: "body ID was not issued by Ralph", id: body.id, at_ms: elapsed()});
        return false;
      }
      if (seen.has(body.id)) {
        state.invalidObservations.push({code: "duplicate-observation-id", detail: "an ID may appear only once per observation", id: body.id, at_ms: elapsed()});
        return false;
      }
      seen.add(body.id);
      bodies.push(body);
    }
    const atMs = elapsed();
    if (state.lastObservationMs !== null && atMs - state.lastObservationMs < OBSERVATION_INTERVAL_MS) {
      return true;
    }
    if (state.observations.length >= MAX_OBSERVATIONS || state.bodySamples + bodies.length > MAX_BODY_SAMPLES) {
      state.invalidObservations.push({code: "observation-limit", detail: `observation trace exceeds ${MAX_OBSERVATIONS} samples`, at_ms: elapsed()});
      return false;
    }
    state.lastObservationMs = atMs;
    state.bodySamples += bodies.length;
    state.observations.push({time_ms: atMs, bodies});
    return true;
  };
  const api = {
    apiVersion: "gates/v1",
    observationVersion: "bodies/v1",
    register(handlers) {
      if (!handlers || typeof handlers.carArrived !== "function" || typeof handlers.pedestrianArrived !== "function") {
        return invalid("invalid-registration", "register() requires carArrived and pedestrianArrived functions");
      }
      state.handlers = {carArrived: handlers.carArrived, pedestrianArrived: handlers.pedestrianArrived};
      return true;
    },
    carFinished(id, exit) { return finish("car", id, exit); },
    pedestrianFinished(id) { return finish("pedestrian", id); },
    observe(bodies) { return observe(bodies); }
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
      invalid_completions: state.invalid.length,
      observation_count: state.observations.length,
      body_sample_count: state.bodySamples,
      invalid_observations: state.invalidObservations.length
    };
  };
  const driver = {
    apiVersion: "gates/v1",
    ready() { return state.handlers !== null; },
    start() {
      state.issued.clear();
      state.completions.clear();
      state.invalid.length = 0;
      state.observations.length = 0;
      state.invalidObservations.length = 0;
      state.bodySamples = 0;
      state.lastObservationMs = null;
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
        invalid: state.invalid.map(item => ({...item})),
        observations: state.observations.map(item => ({
          time_ms: item.time_ms,
          bodies: item.bodies.map(body => ({...body}))
        })),
        invalid_observations: state.invalidObservations.map(item => ({...item}))
      };
    }
  };
  Object.defineProperty(globalThis, "RalphGates", {value: Object.freeze(api), writable: false, configurable: false});
  Object.defineProperty(globalThis, "__RALPH_GATES_DRIVER__", {value: Object.freeze(driver), writable: false, configurable: false});
})();
"""


__all__ = ["GATES_INIT_SCRIPT"]
