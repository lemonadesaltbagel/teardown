"""Print one line per learning run JSON in results/."""
import json, sys, glob
for f in sorted(glob.glob('results/learn_*.json')):
    d = json.load(open(f)); a = d['aalpy']; s = d['sul']; m = s['driver']
    print(f"{d['name']:<48} st={d['states']:>3} rounds={a['learning_rounds']:>2} q_learn={a['queries_learning']:>5} "
          f"q_eq={a['queries_eq_oracle']:>5} steps={a['steps_learning']+a['steps_eq_oracle']:>6} resets={s['real_resets']:>5} "
          f"live={s['live_steps']:>5} replay={s['replay_steps']:>5} hit={s['cache_hit_steps']:>6} "
          f"wall={d['wall_s']:>7}s t_learn={a['learning_time']} t_eq={a['eq_oracle_time']} "
          f"ms/reset={m['ms_per_reset']} ms/act={m['ms_per_action']} ms/snap={m['ms_per_snapshot']}")
