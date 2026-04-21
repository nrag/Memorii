# Memorii Benchmark Report

Run ID: `bench-3300a6883390cdd6`

## Summary
- Total scenarios: 28
- Passed: 9
- Failed: 19

## Aggregate Metrics (By System)
### flat_retrieval_baseline
- blocked_write_accuracy: 1.0000
- conflict_detection_rate: 1.0000
- contradictory_memory_handling_correctness: 0.0000
- correct_preference_for_newer_or_valid_memory: 0.0000
- false_positive_retrieval_rate: 0.0000
- implicit_recall_success_rate: 1.0000
- multi_domain_fanout_correctness: 0.0000
- noise_resilience: 0.3333
- precision_at_k: 0.8667
- recall_at_k: 1.0000
- resume_correctness_under_scale: 1.0000
- retrieval_latency_growth: 120.0000
- retrieval_latency_ms: 33.0000
- retrieval_plan_relevance_accuracy: 1.0000
- retrieval_recall_degradation: 0.0000
- routing_accuracy: 0.0000
- scenario_success_rate: 0.3333
- semantic_pollution_rate: 0.2500
- stale_memory_rejection_rate: 0.0000
- user_memory_pollution_rate: 0.2500
- writeback_candidate_correctness: 0.0000

### memorii
- blocked_write_accuracy: 1.0000
- conflict_detection_rate: 1.0000
- contradictory_memory_handling_correctness: 1.0000
- correct_preference_for_newer_or_valid_memory: 1.0000
- false_positive_retrieval_rate: 0.0000
- implicit_recall_success_rate: 1.0000
- multi_domain_fanout_correctness: 0.0000
- noise_resilience: 0.3333
- precision_at_k: 0.8667
- recall_at_k: 1.0000
- resume_correctness_under_scale: 1.0000
- retrieval_latency_growth: 120.0000
- retrieval_latency_ms: 33.0000
- retrieval_plan_relevance_accuracy: 1.0000
- retrieval_recall_degradation: 0.0000
- routing_accuracy: 0.0000
- scenario_success_rate: 0.8333
- semantic_pollution_rate: 0.0000
- stale_memory_rejection_rate: 1.0000
- user_memory_pollution_rate: 0.0000
- writeback_candidate_correctness: 1.0000

### no_solver_graph_baseline
- blocked_write_accuracy: 1.0000
- conflict_detection_rate: 1.0000
- contradictory_memory_handling_correctness: 0.0000
- correct_preference_for_newer_or_valid_memory: 0.0000
- false_positive_retrieval_rate: 0.0000
- implicit_recall_success_rate: 1.0000
- multi_domain_fanout_correctness: 0.0000
- noise_resilience: 0.3333
- precision_at_k: 0.8667
- recall_at_k: 1.0000
- resume_correctness_under_scale: 1.0000
- retrieval_latency_growth: 120.0000
- retrieval_latency_ms: 33.0000
- retrieval_plan_relevance_accuracy: 1.0000
- retrieval_recall_degradation: 0.0000
- routing_accuracy: 0.0000
- scenario_success_rate: 0.3333
- semantic_pollution_rate: 0.0000
- stale_memory_rejection_rate: 0.0000
- user_memory_pollution_rate: 0.0000
- writeback_candidate_correctness: 0.0000

### transcript_only_baseline
- blocked_write_accuracy: 1.0000
- conflict_detection_rate: 0.0000
- contradictory_memory_handling_correctness: 0.0000
- correct_preference_for_newer_or_valid_memory: 1.0000
- multi_domain_fanout_correctness: 0.0000
- noise_resilience: 0.3333
- precision_at_k: 0.3333
- recall_at_k: 1.0000
- resume_correctness_under_scale: 1.0000
- retrieval_latency_growth: 120.0000
- retrieval_latency_ms: 153.0000
- retrieval_recall_degradation: 0.0000
- routing_accuracy: 0.0000
- scenario_success_rate: 0.0000
- semantic_pollution_rate: 0.0000
- stale_memory_rejection_rate: 1.0000
- user_memory_pollution_rate: 0.0000
- writeback_candidate_correctness: 0.0000

## Baseline Summary
- flat_retrieval_baseline: {'scenario_success_rate': 0.5, 'semantic_pollution_rate': -0.25, 'user_memory_pollution_rate': -0.25, 'conflict_detection_rate': 0.0, 'correct_preference_for_newer_or_valid_memory': 1.0, 'stale_memory_rejection_rate': 1.0, 'contradictory_memory_handling_correctness': 1.0, 'recall_at_k': 0.0, 'precision_at_k': 0.0, 'retrieval_latency_ms': 0.0, 'retrieval_recall_degradation': 0.0, 'retrieval_latency_growth': 0.0, 'resume_correctness_under_scale': 0.0, 'noise_resilience': 0.0, 'routing_accuracy': 0.0, 'blocked_write_accuracy': 0.0, 'multi_domain_fanout_correctness': 0.0, 'writeback_candidate_correctness': 1.0, 'implicit_recall_success_rate': 0.0, 'retrieval_plan_relevance_accuracy': 0.0, 'false_positive_retrieval_rate': 0.0}
- no_solver_graph_baseline: {'scenario_success_rate': 0.5, 'semantic_pollution_rate': 0.0, 'user_memory_pollution_rate': 0.0, 'conflict_detection_rate': 0.0, 'correct_preference_for_newer_or_valid_memory': 1.0, 'stale_memory_rejection_rate': 1.0, 'contradictory_memory_handling_correctness': 1.0, 'recall_at_k': 0.0, 'precision_at_k': 0.0, 'retrieval_latency_ms': 0.0, 'retrieval_recall_degradation': 0.0, 'retrieval_latency_growth': 0.0, 'resume_correctness_under_scale': 0.0, 'noise_resilience': 0.0, 'routing_accuracy': 0.0, 'blocked_write_accuracy': 0.0, 'multi_domain_fanout_correctness': 0.0, 'writeback_candidate_correctness': 1.0, 'implicit_recall_success_rate': 0.0, 'retrieval_plan_relevance_accuracy': 0.0, 'false_positive_retrieval_rate': 0.0}
- transcript_only_baseline: {'scenario_success_rate': 0.75, 'semantic_pollution_rate': 0.0, 'user_memory_pollution_rate': 0.0, 'conflict_detection_rate': 1.0, 'correct_preference_for_newer_or_valid_memory': 0.0, 'stale_memory_rejection_rate': 0.0, 'contradictory_memory_handling_correctness': 1.0, 'recall_at_k': 0.0, 'precision_at_k': 0.0, 'retrieval_latency_ms': 0.0, 'retrieval_recall_degradation': 0.0, 'retrieval_latency_growth': 0.0, 'resume_correctness_under_scale': 0.0, 'noise_resilience': 0.0, 'routing_accuracy': 0.0, 'blocked_write_accuracy': 0.0, 'multi_domain_fanout_correctness': 0.0, 'writeback_candidate_correctness': 1.0}

## Categories
### conflict_resolution (4)
- Metrics systems: flat_retrieval_baseline, memorii, no_solver_graph_baseline, transcript_only_baseline
- Baseline delta systems: flat_retrieval_baseline, no_solver_graph_baseline, transcript_only_baseline
### end_to_end (8)
- Metrics systems: flat_retrieval_baseline, memorii, no_solver_graph_baseline, transcript_only_baseline
- Baseline delta systems: flat_retrieval_baseline, no_solver_graph_baseline, transcript_only_baseline
### implicit_recall (6)
- Metrics systems: flat_retrieval_baseline, memorii, no_solver_graph_baseline, transcript_only_baseline
- Baseline delta systems: flat_retrieval_baseline, no_solver_graph_baseline, transcript_only_baseline
### long_horizon_degradation (4)
- Metrics systems: flat_retrieval_baseline, memorii, no_solver_graph_baseline, transcript_only_baseline
- Baseline delta systems: flat_retrieval_baseline, no_solver_graph_baseline, transcript_only_baseline
### semantic_retrieval (6)
- Metrics systems: flat_retrieval_baseline, memorii, no_solver_graph_baseline, transcript_only_baseline
- Baseline delta systems: flat_retrieval_baseline, no_solver_graph_baseline, transcript_only_baseline

## Scenarios
- `hotpot_control_conflict` (conflict_resolution, flat_retrieval_baseline, component_level) passed=False
- `hotpot_control_conflict` (conflict_resolution, memorii, component_level) passed=True
- `hotpot_control_conflict` (conflict_resolution, no_solver_graph_baseline, component_level) passed=False
- `hotpot_control_conflict` (conflict_resolution, transcript_only_baseline, component_level) passed=False
- `hotpot_control_long_horizon` (long_horizon_degradation, flat_retrieval_baseline, component_level) passed=False
- `hotpot_control_long_horizon` (long_horizon_degradation, memorii, component_level) passed=False
- `hotpot_control_long_horizon` (long_horizon_degradation, no_solver_graph_baseline, component_level) passed=False
- `hotpot_control_long_horizon` (long_horizon_degradation, transcript_only_baseline, component_level) passed=False
- `hotpot_e2e_hp2` (end_to_end, flat_retrieval_baseline, system_level) passed=False
- `hotpot_e2e_hp2` (end_to_end, memorii, system_level) passed=True
- `hotpot_e2e_hp2` (end_to_end, no_solver_graph_baseline, system_level) passed=False
- `hotpot_e2e_hp2` (end_to_end, transcript_only_baseline, system_level) passed=False
- `hotpot_e2e_hp3` (end_to_end, flat_retrieval_baseline, system_level) passed=False
- `hotpot_e2e_hp3` (end_to_end, memorii, system_level) passed=True
- `hotpot_e2e_hp3` (end_to_end, no_solver_graph_baseline, system_level) passed=False
- `hotpot_e2e_hp3` (end_to_end, transcript_only_baseline, system_level) passed=False
- `hotpot_implicit_hp2` (implicit_recall, flat_retrieval_baseline, component_level) passed=True
- `hotpot_implicit_hp2` (implicit_recall, memorii, component_level) passed=True
- `hotpot_implicit_hp2` (implicit_recall, no_solver_graph_baseline, component_level) passed=True
- `hotpot_implicit_hp3` (implicit_recall, flat_retrieval_baseline, component_level) passed=True
- `hotpot_implicit_hp3` (implicit_recall, memorii, component_level) passed=True
- `hotpot_implicit_hp3` (implicit_recall, no_solver_graph_baseline, component_level) passed=True
- `hotpot_semantic_hp2` (semantic_retrieval, flat_retrieval_baseline, component_level) passed=False
- `hotpot_semantic_hp2` (semantic_retrieval, memorii, component_level) passed=False
- `hotpot_semantic_hp2` (semantic_retrieval, no_solver_graph_baseline, component_level) passed=False
- `hotpot_semantic_hp3` (semantic_retrieval, flat_retrieval_baseline, component_level) passed=False
- `hotpot_semantic_hp3` (semantic_retrieval, memorii, component_level) passed=False
- `hotpot_semantic_hp3` (semantic_retrieval, no_solver_graph_baseline, component_level) passed=False