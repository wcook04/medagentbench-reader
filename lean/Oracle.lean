import Potassium
open Potassium

/-- Parse `time,tenths,final` -/
def parseObs (s : String) : Option Obs :=
  match s.splitOn "," with
  | [t, k, f] => do
    let t ← t.toInt?
    let k ← k.toInt?
    pure ⟨t, k, f == "1"⟩
  | _ => none

def render : Outcome → String
  | .noResult => "noResult"
  | .conflict t => s!"conflict {t}"
  | .notLow t v => s!"notLow {t} {v}"
  | .replace t v d r => s!"replace {t} {v} {d} {r}"

/-- One line per decision: `now|t,k,f;t,k,f;…`. Prints the outcome of the proved program `run`. -/
partial def loop (h : IO.FS.Stream) (out : IO.FS.Stream) : IO Unit := do
  let line ← h.getLine
  if line.isEmpty then return
  let line := ((line.splitOn "
").headD "")
  match line.splitOn "|" with
  | [now, rest] =>
    let obs := (if rest.isEmpty then [] else rest.splitOn ";").filterMap parseObs
    match now.toInt? with
    | some n => out.putStrLn (render (run n obs))
    | none => out.putStrLn "error"
  | _ => out.putStrLn "error"
  loop h out

def main : IO Unit := do
  loop (← IO.getStdin) (← IO.getStdout)
