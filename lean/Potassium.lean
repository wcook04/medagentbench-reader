/-
MedAgentBench task 9, the potassium replacement task, as a statement, a program and a proof.

The instruction (benchmark commit 99260117, `test_data_v2.json`, ids `task9_*`):

  "Check patient …'s most recent potassium level. If low, then order replacement potassium
   according to dosing instructions. Also pair this order with a morning serum potassium level
   to be completed the next day at 8am."

  "It's 2023-11-13T10:15:00+00:00 now. … Dosing instructions: for every 0.1 mEq/L (or mmol/L)
   below threshold, order 10 mEq potassium oral repletion) to reach a goal of 3.5 serum level."

Units. Times are whole seconds on one UTC scale. A potassium result is held in tenths of a
mmol/L, the precision of every potassium result in the released records, so 3.5 mmol/L is 35.
Doses are whole mEq.
-/

namespace Potassium

/-- One potassium result as the record holds it. -/
structure Obs where
  /-- When the specimen was taken (`effectiveDateTime`). -/
  time : Int
  /-- The result in tenths of a mmol/L. -/
  tenths : Int
  /-- Whether the record marks the result `final`. -/
  final : Bool
  deriving DecidableEq, Repr

/-- A result counts at decision time `now` when it is final and was taken at or before `now`. -/
def eligible (now : Int) (o : Obs) : Bool :=
  o.final && decide (o.time ≤ now)

/-- "Low" in the instruction: below 3.5 mmol/L. -/
def threshold : Int := 35

/-- "The next day at 8am": 08:00:00 on the calendar day after `now`, on the same UTC scale. -/
def nextMorning (now : Int) : Int :=
  (now / 86400 + 1) * 86400 + 8 * 3600

/-- What the task can come to. -/
inductive Outcome where
  /-- No eligible potassium result exists. Nothing is ordered. -/
  | noResult
  /-- The most recent eligible time carries results with different values.
      The instruction does not say which to use. Nothing is ordered. -/
  | conflict (time : Int)
  /-- The most recent result is 3.5 or above. Nothing is ordered. -/
  | notLow (time tenths : Int)
  /-- The most recent result is below 3.5: order `dose` mEq and a repeat potassium at `repeatAt`. -/
  | replace (time tenths dose repeatAt : Int)
  deriving DecidableEq, Repr

/-- `t` is the most recent eligible time. -/
def IsLatest (now : Int) (obs : List Obs) (t : Int) : Prop :=
  (∃ o ∈ obs, eligible now o = true ∧ o.time = t) ∧
    ∀ o ∈ obs, eligible now o = true → o.time ≤ t

/-- Every eligible result taken at `t` has the value `v`. -/
def AgreeAt (now : Int) (obs : List Obs) (t v : Int) : Prop :=
  ∀ o ∈ obs, eligible now o = true → o.time = t → o.tenths = v

/-- The statement of the task: which outcome the instruction requires for a given record.
    It is written with "for all" and "there exists" over the results, with no algorithm in it. -/
def Spec (now : Int) (obs : List Obs) : Outcome → Prop
  | .noResult => ∀ o ∈ obs, eligible now o = false
  | .conflict t =>
      IsLatest now obs t ∧
        ∃ a ∈ obs, ∃ b ∈ obs, eligible now a = true ∧ eligible now b = true ∧
          a.time = t ∧ b.time = t ∧ a.tenths ≠ b.tenths
  | .notLow t v => IsLatest now obs t ∧ AgreeAt now obs t v ∧ threshold ≤ v
  | .replace t v dose repeatAt =>
      IsLatest now obs t ∧ AgreeAt now obs t v ∧ v < threshold ∧
        dose = 10 * (threshold - v) ∧ repeatAt = nextMorning now

/-! ## The program -/

/-- The latest time in a list of results. -/
def maxTime : List Obs → Option Int
  | [] => none
  | o :: os =>
    match maxTime os with
    | none => some o.time
    | some t => some (if t < o.time then o.time else t)

/-- The program: filter, find the latest time, check the results at that time agree, decide. -/
def run (now : Int) (obs : List Obs) : Outcome :=
  let es := obs.filter (eligible now)
  match maxTime es with
  | none => .noResult
  | some t =>
    match (es.filter fun o => decide (o.time = t)).map (·.tenths) with
    | [] => .noResult
    | v :: rest =>
      if rest.all (fun w => decide (w = v)) then
        if v < threshold then .replace t v (10 * (threshold - v)) (nextMorning now)
        else .notLow t v
      else .conflict t

/-! ## Facts about `maxTime` -/

theorem maxTime_none {os : List Obs} : maxTime os = none ↔ os = [] := by
  cases os with
  | nil => simp [maxTime]
  | cons o os => cases h : maxTime os <;> simp [maxTime, h]

theorem maxTime_spec {os : List Obs} {t : Int} (h : maxTime os = some t) :
    (∃ o ∈ os, o.time = t) ∧ ∀ o ∈ os, o.time ≤ t := by
  induction os generalizing t with
  | nil => simp [maxTime] at h
  | cons o os ih =>
    cases hm : maxTime os with
    | none =>
      have : os = [] := maxTime_none.mp hm
      subst this
      simp [maxTime] at h
      subst h
      simp
    | some u =>
      obtain ⟨⟨w, hw, hwt⟩, hub⟩ := ih hm
      simp [maxTime, hm] at h
      by_cases c : u < o.time
      · simp [c] at h
        subst h
        refine ⟨⟨o, by simp, rfl⟩, ?_⟩
        intro x hx
        rcases List.mem_cons.mp hx with rfl | hx
        · exact Int.le_refl _
        · have := hub x hx; omega
      · simp [c] at h
        subst h
        refine ⟨⟨w, by simp [hw], hwt⟩, ?_⟩
        intro x hx
        rcases List.mem_cons.mp hx with rfl | hx
        · omega
        · exact hub x hx

/-! ## The program meets the statement -/

theorem isLatest_of_maxTime {now : Int} {obs : List Obs} {t : Int}
    (h : maxTime (obs.filter (eligible now)) = some t) : IsLatest now obs t := by
  obtain ⟨⟨w, hw, hwt⟩, hub⟩ := maxTime_spec h
  have hw' := List.mem_filter.mp hw
  refine ⟨⟨w, hw'.1, hw'.2, hwt⟩, ?_⟩
  intro o ho he
  exact hub o (List.mem_filter.mpr ⟨ho, he⟩)

/-- For every record and every decision time, the program's outcome is the one the statement
    requires. -/
theorem run_meets_spec (now : Int) (obs : List Obs) : Spec now obs (run now obs) := by
  unfold run
  simp only
  cases hm : maxTime (obs.filter (eligible now)) with
  | none =>
    have hnil := maxTime_none.mp hm
    simp only [Spec]
    intro o ho
    cases he : eligible now o with
    | false => rfl
    | true =>
      have : o ∈ obs.filter (eligible now) := List.mem_filter.mpr ⟨ho, he⟩
      rw [hnil] at this
      cases this
  | some t =>
    have hl := isLatest_of_maxTime hm
    simp only
    -- the values taken at the latest time
    cases hv : ((obs.filter (eligible now)).filter fun o => decide (o.time = t)).map (·.tenths) with
    | nil =>
      -- impossible: the latest time is attained
      obtain ⟨⟨w, hw, he, hwt⟩, _⟩ := hl
      have : w.tenths ∈ ((obs.filter (eligible now)).filter fun o => decide (o.time = t)).map (·.tenths) := by
        apply List.mem_map.mpr
        exact ⟨w, List.mem_filter.mpr ⟨List.mem_filter.mpr ⟨hw, he⟩, by simp [hwt]⟩, rfl⟩
      rw [hv] at this
      cases this
    | cons v rest =>
      simp only
      -- membership in the value list, both ways
      have mem_iff : ∀ x, x ∈ v :: rest ↔
          ∃ o ∈ obs, eligible now o = true ∧ o.time = t ∧ o.tenths = x := by
        intro x
        rw [← hv]
        constructor
        · intro hx
          obtain ⟨o, ho, rfl⟩ := List.mem_map.mp hx
          have h1 := List.mem_filter.mp ho
          have h2 := List.mem_filter.mp h1.1
          exact ⟨o, h2.1, h2.2, by simpa using h1.2, rfl⟩
        · rintro ⟨o, ho, he, ht, rfl⟩
          exact List.mem_map.mpr
            ⟨o, List.mem_filter.mpr ⟨List.mem_filter.mpr ⟨ho, he⟩, by simp [ht]⟩, rfl⟩
      by_cases hall : rest.all (fun w => decide (w = v)) = true
      · have agree : AgreeAt now obs t v := by
          intro o ho he ht
          have : o.tenths ∈ v :: rest := (mem_iff _).mpr ⟨o, ho, he, ht, rfl⟩
          rcases List.mem_cons.mp this with h | h
          · exact h
          · have := List.all_eq_true.mp hall _ h
            simpa using this
        simp only [hall, ite_true]
        by_cases hlow : v < threshold
        · simp only [hlow, ↓reduceIte]
          exact ⟨hl, agree, hlow, rfl, rfl⟩
        · simp only [hlow, ↓reduceIte]
          exact ⟨hl, agree, by omega⟩
      · simp only [hall, Spec]
        refine ⟨hl, ?_⟩
        -- some later value differs from the first
        have : ∃ w ∈ rest, w ≠ v := by
          apply Classical.byContradiction
          intro hno
          apply hall
          apply List.all_eq_true.mpr
          intro w hw
          have : w = v := Classical.byContradiction fun hne => hno ⟨w, hw, hne⟩
          simp [this]
        obtain ⟨w, hw, hne⟩ := this
        obtain ⟨a, ha, hae, hat, hav⟩ := (mem_iff w).mp (List.mem_cons_of_mem _ hw)
        obtain ⟨b, hb, hbe, hbt, hbv⟩ := (mem_iff v).mp (List.mem_cons_self ..)
        exact ⟨a, ha, b, hb, hae, hbe, hat, hbt, by rw [hav, hbv]; exact hne⟩

/-! ## The statement determines the outcome -/

theorem isLatest_unique {now : Int} {obs : List Obs} {s t : Int}
    (hs : IsLatest now obs s) (ht : IsLatest now obs t) : s = t := by
  obtain ⟨⟨a, ha, hae, hat⟩, hsub⟩ := hs
  obtain ⟨⟨b, hb, hbe, hbt⟩, htub⟩ := ht
  have h1 := hsub b hb hbe
  have h2 := htub a ha hae
  omega

/-- At most one outcome satisfies the statement. With `run_meets_spec` this says the statement
    fixes the outcome completely, so a program cannot satisfy it by always declining. -/
theorem spec_unique {now : Int} {obs : List Obs} {a b : Outcome}
    (ha : Spec now obs a) (hb : Spec now obs b) : a = b := by
  -- helper facts
  have noElig : (∀ o ∈ obs, eligible now o = false) → ∀ t, ¬ IsLatest now obs t := by
    intro h t ⟨⟨o, ho, he, _⟩, _⟩
    rw [h o ho] at he
    cases he
  have agreeVal : ∀ {t v w}, IsLatest now obs t → AgreeAt now obs t v → AgreeAt now obs t w → v = w := by
    intro t v w ⟨⟨o, ho, he, hot⟩, _⟩ hv hw
    rw [← hv o ho he hot, ← hw o ho he hot]
  have agreeNoConflict : ∀ {t v}, AgreeAt now obs t v →
      ¬ ∃ a ∈ obs, ∃ b ∈ obs, eligible now a = true ∧ eligible now b = true ∧
          a.time = t ∧ b.time = t ∧ a.tenths ≠ b.tenths := by
    intro t v hv ⟨a, ha, b, hb, hae, hbe, hat, hbt, hne⟩
    exact hne (by rw [hv a ha hae hat, hv b hb hbe hbt])
  cases a <;> cases b <;> simp only [Spec] at ha hb
  all_goals first
    | rfl
    | exact absurd hb.1 (noElig ha _)
    | exact absurd ha.1 (noElig hb _)
    | skip
  -- conflict / conflict
  · rw [isLatest_unique ha.1 hb.1]
  -- conflict / notLow
  · have := isLatest_unique ha.1 hb.1; subst this
    exact absurd ha.2 (agreeNoConflict hb.2.1)
  -- conflict / replace
  · have := isLatest_unique ha.1 hb.1; subst this
    exact absurd ha.2 (agreeNoConflict hb.2.1)
  -- notLow / conflict
  · have := isLatest_unique ha.1 hb.1; subst this
    exact absurd hb.2 (agreeNoConflict ha.2.1)
  -- notLow / notLow
  · have := isLatest_unique ha.1 hb.1; subst this
    rw [agreeVal ha.1 ha.2.1 hb.2.1]
  -- notLow / replace
  · have := isLatest_unique ha.1 hb.1; subst this
    have := agreeVal ha.1 ha.2.1 hb.2.1; subst this
    have h1 := ha.2.2; have h2 := hb.2.2.1
    omega
  -- replace / conflict
  · have := isLatest_unique ha.1 hb.1; subst this
    exact absurd hb.2 (agreeNoConflict ha.2.1)
  -- replace / notLow
  · have := isLatest_unique ha.1 hb.1; subst this
    have := agreeVal ha.1 ha.2.1 hb.2.1; subst this
    have h1 := ha.2.2.1; have h2 := hb.2.2
    omega
  -- replace / replace
  · have := isLatest_unique ha.1 hb.1; subst this
    have := agreeVal ha.1 ha.2.1 hb.2.1; subst this
    obtain ⟨_, _, _, hd, hr⟩ := ha
    obtain ⟨_, _, _, hd', hr'⟩ := hb
    rw [hd, hr, hd', hr']

/-- The program's outcome is the only outcome the statement allows. -/
theorem run_is_the_answer {now : Int} {obs : List Obs} {out : Outcome} :
    Spec now obs out ↔ out = run now obs :=
  ⟨fun h => spec_unique h (run_meets_spec now obs), fun h => h ▸ run_meets_spec now obs⟩

/-! ## Consequences a reader can check against the instruction -/

/-- The order in which the record returns its results does not matter. -/
theorem run_order_free {now : Int} {obs obs' : List Obs}
    (h : ∀ o, o ∈ obs ↔ o ∈ obs') : run now obs = run now obs' := by
  apply spec_unique (obs := obs') (now := now) _ (run_meets_spec now obs')
  have hs := run_meets_spec now obs
  have latest : ∀ t, IsLatest now obs t → IsLatest now obs' t := by
    intro t ⟨⟨o, ho, he, hot⟩, hub⟩
    exact ⟨⟨o, (h o).mp ho, he, hot⟩, fun x hx => hub x ((h x).mpr hx)⟩
  have agree : ∀ t v, AgreeAt now obs t v → AgreeAt now obs' t v :=
    fun t v hv o ho => hv o ((h o).mpr ho)
  cases hr : run now obs <;> rw [hr] at hs <;> simp only [Spec] at hs ⊢
  · exact fun o ho => hs o ((h o).mpr ho)
  · obtain ⟨hl, a, ha, b, hb, rest⟩ := hs
    exact ⟨latest _ hl, a, (h a).mp ha, b, (h b).mp hb, rest⟩
  · exact ⟨latest _ hs.1, agree _ _ hs.2.1, hs.2.2⟩
  · exact ⟨latest _ hs.1, agree _ _ hs.2.1, hs.2.2⟩

/-- Whenever replacement is ordered the dose is a positive multiple of 10 mEq. -/
theorem dose_shape {now : Int} {obs : List Obs} {t v dose r : Int}
    (h : run now obs = .replace t v dose r) : 10 ≤ dose ∧ dose % 10 = 0 := by
  have hs := run_meets_spec now obs
  rw [h] at hs
  obtain ⟨_, _, hlow, hd, _⟩ := hs
  unfold threshold at hlow hd
  omega

/-- One low result on its own: the program orders 10 mEq for each tenth below 3.5. -/
theorem run_single (v : Int) (h : v < threshold) :
    run 0 [⟨0, v, true⟩] = .replace 0 v (10 * (threshold - v)) (nextMorning 0) := by
  simp [run, maxTime, eligible, h]

/-- The dose is fixed by the result alone: 10 mEq for each tenth of a mmol/L below 3.5. -/
theorem dose_exact {now : Int} {obs : List Obs} {t v dose r : Int}
    (h : run now obs = .replace t v dose r) : dose = 10 * (35 - v) := by
  have hs := run_meets_spec now obs
  rw [h] at hs
  obtain ⟨_, _, _, hd, _⟩ := hs
  unfold threshold at hd
  exact hd

/-- The instruction writes no upper limit on the dose. The only limit comes from a result not
    being negative, and that limit is 350 mEq, reached at a recorded result of 0.0. -/
theorem dose_limit {now : Int} {obs : List Obs} {t v dose r : Int}
    (h : run now obs = .replace t v dose r) (nonneg : 0 ≤ v) : dose ≤ 350 := by
  have := dose_exact h
  omega

theorem dose_limit_reached : run 0 [⟨0, 0, true⟩] = .replace 0 0 350 (nextMorning 0) := by
  decide

/-- The single amount ordered is more than `m` mEq exactly when the result is more than `m / 10`
    tenths below 3.5. With `m = 20`: more than 20 mEq exactly when the result is below 3.3. -/
theorem dose_over_20 {now : Int} {obs : List Obs} {t v dose r : Int}
    (h : run now obs = .replace t v dose r) : 20 < dose ↔ v < 33 := by
  have := dose_exact h
  omega

/-- Results that do not count cannot change the outcome: two records with the same final
    results taken at or before `now` get the same outcome, whatever else they hold. -/
theorem run_reads_only_eligible {now : Int} {obs obs' : List Obs}
    (h : obs.filter (eligible now) = obs'.filter (eligible now)) : run now obs = run now obs' := by
  unfold run
  rw [h]

/-- A shorter view of the record is enough when it keeps every counted result taken at the latest
    time. If the view holds nothing that is not in the record, and holds every final result that no
    other counted result is later than, then the program's outcome on the view is its outcome on
    the whole record. Nothing left out of such a view can change the answer. -/
theorem run_sufficient_view {now : Int} {obs view : List Obs}
    (sub : ∀ o ∈ view, o ∈ obs)
    (keeps : ∀ o ∈ obs, eligible now o = true →
      (∀ p ∈ obs, eligible now p = true → p.time ≤ o.time) → o ∈ view) :
    run now view = run now obs := by
  apply spec_unique (obs := view) (now := now) (run_meets_spec now view)
  have hs := run_meets_spec now obs
  have latest : ∀ t, IsLatest now obs t → IsLatest now view t := by
    intro t ⟨⟨o, ho, he, hot⟩, hub⟩
    refine ⟨⟨o, keeps o ho he (fun p hp hpe => by rw [hot]; exact hub p hp hpe), he, hot⟩, ?_⟩
    intro x hx hxe
    exact hub x (sub x hx) hxe
  have agree : ∀ t v, AgreeAt now obs t v → AgreeAt now view t v :=
    fun t v hv o ho => hv o (sub o ho)
  cases hr : run now obs <;> rw [hr] at hs <;> simp only [Spec] at hs ⊢
  · exact fun o ho => hs o (sub o ho)
  · obtain ⟨hl, a, ha, b, hb, hae, hbe, hat, hbt, hne⟩ := hs
    have hub := hl.2
    exact ⟨latest _ hl, a, keeps a ha hae (fun p hp hpe => by rw [hat]; exact hub p hp hpe), b,
      keeps b hb hbe (fun p hp hpe => by rw [hbt]; exact hub p hp hpe), hae, hbe, hat, hbt, hne⟩
  · exact ⟨latest _ hs.1, agree _ _ hs.2.1, hs.2.2⟩
  · exact ⟨latest _ hs.1, agree _ _ hs.2.1, hs.2.2⟩

/-- Keeping only some of the newest results is not such a view in general: with two counted
    results at the latest time that differ, a view holding one of them gets a different outcome. -/
theorem truncated_view_can_differ :
    ∃ (now : Int) (obs view : List Obs), (∀ o ∈ view, o ∈ obs) ∧ run now view ≠ run now obs := by
  refine ⟨0, [⟨0, 31, true⟩, ⟨0, 32, true⟩], [⟨0, 31, true⟩], by simp, by decide⟩

/-- The repeat test falls at 08:00:00 on the next calendar day. -/
theorem nextMorning_shape (now : Int) :
    nextMorning now % 86400 = 8 * 3600 ∧ nextMorning now / 86400 = now / 86400 + 1 := by
  unfold nextMorning
  omega

/-! ## Stanford's grader, modelled, and where it agrees

The released grader's reference selection (`refsol.py`, `task9`): read every returned row, keep
the first row with the strictly latest time, never read status, apply no upper time bound. -/

/-- The grader's selection: the first row holding the strictly latest time. -/
def graderPick : List Obs → Option Obs
  | [] => none
  | o :: os =>
    match graderPick os with
    | none => some o
    | some p => some (if o.time ≥ p.time then o else p)

/-- What the grader requires, as an outcome, from its selected row. -/
def graderOutcome (now : Int) (obs : List Obs) : Outcome :=
  match graderPick obs with
  | none => .noResult
  | some p =>
    if p.tenths < threshold then
      .replace p.time p.tenths (10 * (threshold - p.tenths)) (nextMorning now)
    else .notLow p.time p.tenths

theorem graderPick_spec {os : List Obs} {p : Obs} (h : graderPick os = some p) :
    p ∈ os ∧ ∀ o ∈ os, o.time ≤ p.time := by
  induction os generalizing p with
  | nil => simp [graderPick] at h
  | cons o os ih =>
    cases hp : graderPick os with
    | none =>
      have : os = [] := by
        cases os with
        | nil => rfl
        | cons x xs => cases hx : graderPick xs <;> simp [graderPick, hx] at hp
      subst this
      simp [graderPick] at h
      subst h
      simp
    | some q =>
      obtain ⟨hq, hub⟩ := ih hp
      simp [graderPick, hp] at h
      by_cases c : q.time ≤ o.time
      · simp [c] at h
        subst h
        refine ⟨by simp, ?_⟩
        intro x hx
        rcases List.mem_cons.mp hx with rfl | hx
        · exact Int.le_refl _
        · have := hub x hx; omega
      · simp [c] at h
        subst h
        refine ⟨by simp [hq], ?_⟩
        intro x hx
        rcases List.mem_cons.mp hx with rfl | hx
        · omega
        · exact hub x hx

theorem graderPick_none {os : List Obs} : graderPick os = none ↔ os = [] := by
  cases os with
  | nil => simp [graderPick]
  | cons o os => cases h : graderPick os <;> simp [graderPick, h]

/-- The grader requires the same outcome as the statement on every record in which each result
    is final, none is dated after the decision time, and results taken at the same time agree.
    The released potassium results meet the first two conditions; the third fails in places. -/
theorem grader_agrees {now : Int} {obs : List Obs}
    (allEligible : ∀ o ∈ obs, eligible now o = true)
    (noConflict : ∀ a ∈ obs, ∀ b ∈ obs, a.time = b.time → a.tenths = b.tenths) :
    graderOutcome now obs = run now obs := by
  apply spec_unique (now := now) (obs := obs) _ (run_meets_spec now obs)
  unfold graderOutcome
  cases hp : graderPick obs with
  | none =>
    have := graderPick_none.mp hp
    subst this
    simp [Spec]
  | some p =>
    obtain ⟨hmem, hub⟩ := graderPick_spec hp
    have hl : IsLatest now obs p.time :=
      ⟨⟨p, hmem, allEligible p hmem, rfl⟩, fun o ho _ => hub o ho⟩
    have ha : AgreeAt now obs p.time p.tenths :=
      fun o ho _ hot => noConflict o ho p hmem hot
    simp only
    by_cases hlow : p.tenths < threshold
    · simp only [hlow, ↓reduceIte]
      exact ⟨hl, ha, hlow, rfl, rfl⟩
    · simp only [hlow, ↓reduceIte]
      exact ⟨hl, ha, by omega⟩

/-- Two results taken at the same time with different values: the grader's requirement depends on
    which the server returns first. -/
theorem grader_order_dependent :
    ∃ (now : Int) (a b : Obs),
      graderOutcome now [a, b] ≠ graderOutcome now [b, a] ∧ run now [a, b] = run now [b, a] := by
  refine ⟨0, ⟨0, 33, true⟩, ⟨0, 36, true⟩, by decide, by decide⟩

/-- A result dated after the decision time: the grader uses it, the statement does not. -/
theorem grader_takes_future_result :
    ∃ (now : Int) (obs : List Obs), graderOutcome now obs ≠ run now obs := by
  refine ⟨0, [⟨-3600, 40, true⟩, ⟨3600, 30, true⟩], by decide⟩

end Potassium
