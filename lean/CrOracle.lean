import Creatinine
open Creatinine

/-- Parse `time,hundredths,final` -/
def parseObs (s : String) : Option Obs :=
  match s.splitOn "," with
  | [t, v, f] => do
    let t ← t.toInt?
    let v ← v.toInt?
    pure ⟨t, v, f == "1"⟩
  | _ => none

def render : Outcome → String
  | .noRise => "noRise"
  | .rise t a b => s!"rise {t} {a.time} {a.hundredths} {b.time} {b.hundredths}"

/-- One line per decision: `now|t,v,f;t,v,f;…`. Prints the outcome of the proved program `run`.
    A malformed result or line prints `error` rather than being dropped. -/
partial def loop (h : IO.FS.Stream) (out : IO.FS.Stream) : IO Unit := do
  let line ← h.getLine
  if line.isEmpty then return
  let line := ((line.splitOn "\n").headD "")
  match line.splitOn "|" with
  | [now, rest] =>
    let parts := if rest.isEmpty then [] else rest.splitOn ";"
    let obs := parts.filterMap parseObs
    match now.toInt? with
    | some n =>
      if obs.length == parts.length then out.putStrLn (render (run n obs))
      else out.putStrLn "error"
    | none => out.putStrLn "error"
  | _ => out.putStrLn "error"
  loop h out

def main : IO Unit := do
  loop (← IO.getStdin) (← IO.getStdout)
