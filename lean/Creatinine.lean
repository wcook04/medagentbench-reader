/-
A creatinine rise of at least 0.3 mg/dL within 48 hours, as a statement, a program and a proof.

Source: KDIGO Clinical Practice Guideline for Acute Kidney Injury (2012). Its definition of acute
kidney injury has three criteria, any one of which suffices:
  (1) serum creatinine rises by at least 0.3 mg/dL within 48 hours;
  (2) serum creatinine rises to at least 1.5 times baseline, known or presumed to have occurred
      within the prior 7 days;
  (3) urine volume below 0.5 mL/kg/h for 6 hours.

This file covers criterion (1) only, and only as a finding about the record. It does NOT diagnose
acute kidney injury: criteria (2) and (3), staging, and clinical judgement are out of scope, and a
record without such a rise may still meet criterion (2) or (3). The finding is exactly:

  "the record holds two creatinine results, the later taken at most 48 hours after the earlier,
   with the later at least 0.3 mg/dL higher".

Units. Times are whole seconds on one UTC scale (when the specimen was taken). A creatinine result
is held in hundredths of a mg/dL, the precision of every mg/dL creatinine result in the released
records, so 0.3 mg/dL is 30 and 48 hours is 172800 seconds.
-/

namespace Creatinine

/-- One creatinine result as the record holds it. -/
structure Obs where
  /-- When the specimen was taken. -/
  time : Int
  /-- The result in hundredths of a mg/dL. -/
  hundredths : Int
  /-- Whether the record marks the result `final`. -/
  final : Bool
  deriving DecidableEq, Repr

/-- A result counts at decision time `now` when it is final and was taken at or before `now`. -/
def eligible (now : Int) (o : Obs) : Bool :=
  o.final && decide (o.time ≤ now)

/-- 48 hours in seconds. -/
def window : Int := 172800

/-- 0.3 mg/dL in hundredths. -/
def minRise : Int := 30

/-- The pair `a`, `b` shows the rise: both are results in the record that count at `now`, `b` was
    taken after `a` and at most 48 hours after it, and `b` is at least 0.30 mg/dL higher. -/
def Qualifies (now : Int) (obs : List Obs) (a b : Obs) : Prop :=
  a ∈ obs ∧ b ∈ obs ∧ eligible now a = true ∧ eligible now b = true ∧
    a.time < b.time ∧ b.time - a.time ≤ window ∧ b.hundredths - a.hundredths ≥ minRise

/-- `T` is the first moment the blood shows the rise: some qualifying pair has its later specimen
    taken at `T`, and no qualifying pair has its later specimen taken before `T`. -/
def IsFirstRise (now : Int) (obs : List Obs) (T : Int) : Prop :=
  (∃ a b, Qualifies now obs a b ∧ b.time = T) ∧ ∀ a b, Qualifies now obs a b → T ≤ b.time

/-- What the check can come to. -/
inductive Outcome where
  /-- The record holds no qualifying pair. This says nothing about criteria (2) or (3). -/
  | noRise
  /-- The first rise is shown at `firstAt`, witnessed by the pair `earlier`, `later`. -/
  | rise (firstAt : Int) (earlier later : Obs)
  deriving DecidableEq, Repr

/-- The time of the first rise, if there is one. -/
def Outcome.firstAt? : Outcome → Option Int
  | .noRise => none
  | .rise T _ _ => some T

/-- The statement: which outcomes the criterion allows for a given record, written with "for all"
    and "there exists" over the results, with no algorithm in it. -/
def Spec (now : Int) (obs : List Obs) : Outcome → Prop
  | .noRise => ¬ ∃ a b, Qualifies now obs a b
  | .rise T a b => IsFirstRise now obs T ∧ Qualifies now obs a b ∧ b.time = T

/-! ## The program -/

/-- The time and value part of the test on an ordered pair. -/
def gapOk (a b : Obs) : Bool :=
  decide (a.time < b.time) && decide (b.time - a.time ≤ window) &&
    decide (b.hundredths - a.hundredths ≥ minRise)

/-- Every ordered pair of results that count at `now` and pass the test. -/
def pairs (now : Int) (obs : List Obs) : List (Obs × Obs) :=
  let es := obs.filter (eligible now)
  (es.flatMap fun a => es.map fun b => (a, b)).filter fun p => gapOk p.1 p.2

/-- The pair whose later specimen was taken first (the earliest in the list among ties). -/
def firstPair : List (Obs × Obs) → Option (Obs × Obs)
  | [] => none
  | p :: ps =>
    match firstPair ps with
    | none => some p
    | some q => some (if p.2.time ≤ q.2.time then p else q)

/-- The program: list every qualifying pair, report the one whose later specimen came first. -/
def run (now : Int) (obs : List Obs) : Outcome :=
  match firstPair (pairs now obs) with
  | none => .noRise
  | some (a, b) => .rise b.time a b

/-! ## Facts about the program's parts -/

theorem gapOk_iff (a b : Obs) :
    gapOk a b = true ↔
      a.time < b.time ∧ b.time - a.time ≤ window ∧ b.hundredths - a.hundredths ≥ minRise := by
  simp [gapOk, Bool.and_eq_true, decide_eq_true_eq, and_assoc]

theorem mem_pairs {now : Int} {obs : List Obs} {a b : Obs} :
    (a, b) ∈ pairs now obs ↔ Qualifies now obs a b := by
  unfold pairs Qualifies
  simp only [List.mem_filter, List.mem_flatMap, List.mem_map, Prod.mk.injEq, gapOk_iff]
  constructor
  · rintro ⟨⟨x, ⟨hx, hxe⟩, y, ⟨hy, hye⟩, rfl, rfl⟩, g⟩
    exact ⟨hx, hy, hxe, hye, g⟩
  · rintro ⟨ha, hb, hae, hbe, g⟩
    exact ⟨⟨a, ⟨ha, hae⟩, b, ⟨hb, hbe⟩, rfl, rfl⟩, g⟩

theorem firstPair_none {ps : List (Obs × Obs)} : firstPair ps = none ↔ ps = [] := by
  cases ps with
  | nil => simp [firstPair]
  | cons p ps => cases h : firstPair ps <;> simp [firstPair, h]

theorem firstPair_spec {ps : List (Obs × Obs)} {p : Obs × Obs} (h : firstPair ps = some p) :
    p ∈ ps ∧ ∀ q ∈ ps, p.2.time ≤ q.2.time := by
  induction ps generalizing p with
  | nil => simp [firstPair] at h
  | cons x ps ih =>
    cases hm : firstPair ps with
    | none =>
      have : ps = [] := firstPair_none.mp hm
      subst this
      simp [firstPair] at h
      subst h
      simp
    | some q =>
      obtain ⟨hq, hlb⟩ := ih hm
      simp [firstPair, hm] at h
      by_cases c : x.2.time ≤ q.2.time
      · simp [c] at h
        subst h
        refine ⟨by simp, ?_⟩
        intro y hy
        rcases List.mem_cons.mp hy with rfl | hy
        · exact Int.le_refl _
        · have := hlb y hy; omega
      · simp [c] at h
        subst h
        refine ⟨by simp [hq], ?_⟩
        intro y hy
        rcases List.mem_cons.mp hy with rfl | hy
        · omega
        · exact hlb y hy

/-! ## The program meets the statement -/

/-- For every record and every decision time, the program's outcome is one the statement allows:
    it reports "no rise" exactly when no pair of results shows a rise of at least 0.30 mg/dL within
    48 hours, and otherwise it reports the first time the blood showed such a rise together with a
    pair that shows it. -/
theorem run_meets_spec (now : Int) (obs : List Obs) : Spec now obs (run now obs) := by
  unfold run
  cases hm : firstPair (pairs now obs) with
  | none =>
    have hnil := firstPair_none.mp hm
    simp only [Spec]
    rintro ⟨a, b, hq⟩
    have := mem_pairs.mpr hq
    rw [hnil] at this
    cases this
  | some p =>
    obtain ⟨a, b⟩ := p
    obtain ⟨hmem, hlb⟩ := firstPair_spec hm
    have hq : Qualifies now obs a b := mem_pairs.mp hmem
    show IsFirstRise now obs b.time ∧ Qualifies now obs a b ∧ b.time = b.time
    exact ⟨⟨⟨a, b, hq, rfl⟩, fun x y hxy => hlb (x, y) (mem_pairs.mpr hxy)⟩, hq, rfl⟩

/-! ## What the statement fixes -/

theorem isFirstRise_unique {now : Int} {obs : List Obs} {S T : Int}
    (hS : IsFirstRise now obs S) (hT : IsFirstRise now obs T) : S = T := by
  obtain ⟨⟨a, b, hab, hbS⟩, hS'⟩ := hS
  obtain ⟨⟨c, d, hcd, hdT⟩, hT'⟩ := hT
  have h1 := hS' c d hcd
  have h2 := hT' a b hab
  omega

/-- The statement fixes whether there is a rise and, if there is, the time it was first shown:
    any two outcomes it allows agree on both. It does not fix the witnessing pair, since several
    pairs can show a rise at the same first time (see `witness_not_unique`). -/
theorem rise_time_unique {now : Int} {obs : List Obs} {o₁ o₂ : Outcome}
    (h₁ : Spec now obs o₁) (h₂ : Spec now obs o₂) : o₁.firstAt? = o₂.firstAt? := by
  cases o₁ with
  | noRise =>
    cases o₂ with
    | noRise => rfl
    | rise T a b => exact absurd ⟨a, b, h₂.2.1⟩ h₁
  | rise S a b =>
    cases o₂ with
    | noRise => exact absurd ⟨a, b, h₁.2.1⟩ h₂
    | rise T c d =>
      simp only [Outcome.firstAt?, Option.some.injEq]
      exact isFirstRise_unique h₁.1 h₂.1

/-- The program's answer to "is there a rise, and when was it first shown" is the only answer the
    statement allows. -/
theorem run_time_is_the_answer {now : Int} {obs : List Obs} {out : Outcome}
    (h : Spec now obs out) : out.firstAt? = (run now obs).firstAt? :=
  rise_time_unique h (run_meets_spec now obs)

/-- Two pairs can witness the same first rise, so the statement allows more than one outcome:
    results of 1.00 at 0 h and 1.00 at 1 h are each followed by 2.00 at 2 h. -/
theorem witness_not_unique :
    ∃ (now : Int) (obs : List Obs) (a a' b : Obs), a ≠ a' ∧
      Spec now obs (.rise b.time a b) ∧ Spec now obs (.rise b.time a' b) := by
  let a : Obs := ⟨0, 100, true⟩
  let a' : Obs := ⟨3600, 100, true⟩
  let b : Obs := ⟨7200, 200, true⟩
  have qa : Qualifies 7200 [a, a', b] a b := by
    simp [Qualifies, a, b, eligible, window, minRise]
  have qa' : Qualifies 7200 [a, a', b] a' b := by
    simp [Qualifies, a', b, eligible, window, minRise]
  have first : IsFirstRise 7200 [a, a', b] b.time := by
    refine ⟨⟨a, b, qa, rfl⟩, ?_⟩
    rintro x y ⟨hx, hy, -, -, hlt, -, hup⟩
    simp only [List.mem_cons, List.not_mem_nil, or_false] at hx hy
    rcases hx with rfl | rfl | rfl <;> rcases hy with rfl | rfl | rfl <;>
      simp_all [a, a', b, minRise]
  exact ⟨7200, [a, a', b], a, a', b, by decide, ⟨first, qa, rfl⟩, ⟨first, qa', rfl⟩⟩

/-! ## Consequences a reader can check against the criterion -/

/-- A reported rise is real: both results are in the record, both are final and taken at or before
    the decision time, the later was taken after the earlier and at most 48 hours after it, the
    later is at least 0.30 mg/dL higher, and the reported time is when the later was taken. -/
theorem run_sound {now : Int} {obs : List Obs} {T : Int} {a b : Obs}
    (h : run now obs = .rise T a b) :
    a ∈ obs ∧ b ∈ obs ∧ a.final = true ∧ b.final = true ∧ a.time ≤ now ∧ b.time ≤ now ∧
      a.time < b.time ∧ b.time - a.time ≤ 172800 ∧ b.hundredths - a.hundredths ≥ 30 ∧
      b.time = T := by
  have hs := run_meets_spec now obs
  rw [h] at hs
  obtain ⟨_, ⟨ha, hb, hae, hbe, hlt, hw, hr⟩, hT⟩ := hs
  simp only [eligible, Bool.and_eq_true, decide_eq_true_eq] at hae hbe
  exact ⟨ha, hb, hae.1, hbe.1, hae.2, hbe.2, hlt, hw, hr, hT⟩

/-- A reported rise is the first one: no pair in the record shows a rise whose later specimen was
    taken before the reported time. -/
theorem run_first {now : Int} {obs : List Obs} {T : Int} {a b : Obs}
    (h : run now obs = .rise T a b) : ∀ x y, Qualifies now obs x y → T ≤ y.time := by
  have hs := run_meets_spec now obs
  rw [h] at hs
  exact hs.1.2

/-- No rise is missed: if any pair of results shows a rise of at least 0.30 mg/dL within 48 hours,
    the program reports a rise. -/
theorem run_complete {now : Int} {obs : List Obs} (h : ∃ a b, Qualifies now obs a b) :
    ∃ T a b, run now obs = .rise T a b := by
  have hs := run_meets_spec now obs
  cases hr : run now obs with
  | noRise => rw [hr] at hs; exact absurd h hs
  | rise T a b => exact ⟨T, a, b, rfl⟩

/-- The order in which the record returns its results does not change whether a rise is reported
    or the time it was first shown. (The witnessing pair may differ when several pairs tie.) -/
theorem run_order_free {now : Int} {obs obs' : List Obs}
    (h : ∀ o, o ∈ obs ↔ o ∈ obs') : (run now obs).firstAt? = (run now obs').firstAt? := by
  have q : ∀ a b, Qualifies now obs a b ↔ Qualifies now obs' a b := by
    intro a b
    unfold Qualifies
    rw [h a, h b]
  have transfer : ∀ out, Spec now obs out → Spec now obs' out := by
    intro out hs
    cases out with
    | noRise =>
      simp only [Spec] at hs ⊢
      rintro ⟨a, b, hab⟩
      exact hs ⟨a, b, (q a b).mpr hab⟩
    | rise T a b =>
      obtain ⟨⟨⟨x, y, hxy, hyT⟩, hlb⟩, hab, hbT⟩ := hs
      exact ⟨⟨⟨x, y, (q x y).mp hxy, hyT⟩, fun u v huv => hlb u v ((q u v).mpr huv)⟩,
        (q a b).mp hab, hbT⟩
  exact rise_time_unique (transfer _ (run_meets_spec now obs)) (run_meets_spec now obs')

/-- In particular, any reordering (permutation) of the record. -/
theorem run_perm {now : Int} {obs obs' : List Obs} (h : obs.Perm obs') :
    (run now obs).firstAt? = (run now obs').firstAt? :=
  run_order_free fun _ => h.mem_iff

/-- Results that do not count cannot change the outcome: two records with the same final results
    taken at or before `now`, in the same order, get the same outcome, whatever else they hold. -/
theorem run_reads_only_eligible {now : Int} {obs obs' : List Obs}
    (h : obs.filter (eligible now) = obs'.filter (eligible now)) : run now obs = run now obs' := by
  unfold run pairs
  simp only
  rw [h]

/-- A single result can never show a rise: the criterion needs two results. So "no rise" on such a
    record means only that the record cannot establish the finding, not that kidney function is
    stable, and not that acute kidney injury is excluded. -/
theorem run_single (now : Int) (o : Obs) : run now [o] = .noRise := by
  have hs := run_meets_spec now [o]
  cases hr : run now [o] with
  | noRise => rfl
  | rise T a b =>
    rw [hr] at hs
    obtain ⟨_, ⟨ha, hb, -, -, hlt, -, -⟩, -⟩ := hs
    simp only [List.mem_singleton] at ha hb
    subst ha; subst hb
    exact absurd hlt (Int.lt_irrefl _)

/-- A record with no results shows no rise. -/
theorem run_empty (now : Int) : run now [] = .noRise := by
  simp [run, pairs, firstPair]

/-- The boundaries are inclusive: a rise of exactly 0.30 mg/dL over exactly 48 hours counts, and
    0.29 mg/dL, or 48 hours and one second, does not. -/
theorem boundaries :
    run 172800 [⟨0, 100, true⟩, ⟨172800, 130, true⟩] = .rise 172800 ⟨0, 100, true⟩ ⟨172800, 130, true⟩ ∧
    run 172801 [⟨0, 100, true⟩, ⟨172801, 130, true⟩] = .noRise ∧
    run 172800 [⟨0, 100, true⟩, ⟨172800, 129, true⟩] = .noRise := by
  decide

/-- A fall is not a rise: the later result must be the higher one. -/
theorem fall_is_not_rise :
    run 3600 [⟨0, 200, true⟩, ⟨3600, 100, true⟩] = .noRise := by
  decide

end Creatinine
