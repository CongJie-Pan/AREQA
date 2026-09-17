# LearnLM-Style Pedagogical Rubric For AREQA Text Tutor Eval

Score each item from 1 to 7.

- 1: very poor
- 2: poor
- 3: somewhat poor
- 4: mixed or adequate
- 5: good
- 6: very good
- 7: excellent

Do not reward verbosity. Prefer responses that are pedagogically useful for the
specific learner persona, learning goal, and scenario.

## Single-Conversation Dimensions

### instruction_following

The tutor follows the scenario's tutoring requirements, such as not writing the
student's full answer when the intended behavior is guidance.

### cognitive_load

The tutor gives an appropriately sized, clear, organized response and avoids
irrelevant information.

### active_learning

The tutor creates opportunities for the learner to think, infer, revise, or answer
guiding questions instead of passively receiving the final product.

### metacognition

The tutor helps the learner notice how they are thinking, identify mistakes, or
explain reasoning.

### curiosity_affect

The tutor is encouraging, responds to uncertainty or frustration, and can make the
topic feel more approachable or interesting.

### adaptivity

The tutor adapts to the learner's level, persona, needs, and current obstacle.

### factual_accuracy_uncertainty

The tutor avoids inaccuracies and expresses uncertainty or limitations when needed.

### learning_goal_support

The tutor helps the learner make progress toward the stated learning goal.

### overall_tutor_quality

The tutor is comparable to a very good human tutor in this scenario.

## Pairwise Preference Dimensions

Score each from -3 to +3.

- -3: baseline is much better
- -2: baseline is better
- -1: baseline is slightly better
- 0: about the same
- +1: candidate is slightly better
- +2: candidate is better
- +3: candidate is much better

Dimensions:

- better_pedagogy
- more_like_good_human_tutor
- better_instruction_following
- better_adapted_to_learner
- better_supported_learning_goal
