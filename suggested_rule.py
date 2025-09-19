```python
    def compile_new_faculty_day_off_specific(self, model, variables, cfg, **kwargs):
        """
        Handles requests like "FAC001 Fri off"
        """
        terms = []
        conf = cfg.get("faculty_day_off_specific", {})
        if self._enabled(conf):
            requests = self._set_from_params(conf.get("params", {}), "requests")
            for req in requests:
                try:
                    faculty_id, day = req.split()
                    day = day.upper()  # Normalize to uppercase
                    for rec in self._iter_assignments(variables):
                        if rec["faculty_id"] == faculty_id and rec["day"] == day:
                            v = model.NewBoolVar(f"p_fac_day_off_{faculty_id}_{day}")
                            model.Add(rec["var"] == 1).OnlyEnforceIf(v)
                            model.Add(rec["var"] == 0).OnlyEnforceIf(v.Not())
                            terms.append(("faculty_day_off_specific", 100, v)) #Fixed weight for now.  Could be configurable
                except ValueError:
                    print(f"Warning: Invalid faculty day off request: {req}")

        return terms

```
