# Agentic Task Reasoning Effort 실험 결과

## 1. 실험 개요

Agentic workflow의 주요 task를 `plan`, `react`, `tool`, `verify`로 나누고, 각 task에서 reasoning effort를 `none`, `low`, `medium`으로 변경하여 성능과 비용을 비교하였다.

각 설정당 `n=25`로 평가하였다.

평가 지표:

- **success**: task 최종 성공률
- **latency_sec**: 평균 실행 시간
- **tool_calls**: 평균 tool 호출 횟수
- **reasoning_tokens**: reasoning에 사용된 평균 token 수
- **output_tokens**: 최종 출력 평균 token 수
- **tool_accuracy**: 올바른 tool을 선택한 비율
- **trajectory_recall**: 필요한 intermediate trajectory를 수행한 비율
- **recovery_rate**: 실패 상황에서 정상적으로 recovery한 비율

---

## 2. 전체 결과

| Task | Effort | Success | Latency | Tool Calls | Reasoning Tokens | Output Tokens | Tool Acc. | Trajectory Recall | Recovery |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Plan | none | 0.00 | **3.844s** | **1.84** | **0.00** | **41.48** | - | - | - |
| Plan | low | 0.00 | 5.663s | 2.24 | 52.52 | 96.88 | - | - | - |
| Plan | medium | 0.00 | 7.119s | 2.48 | 91.32 | 133.92 | - | - | - |
| ReAct | none | 0.00 | 3.717s | 1.00 | 0.00 | 26.48 | - | 0.00 | - |
| ReAct | low | 0.00 | **3.301s** | 1.00 | 0.00 | **26.08** | - | 0.00 | - |
| ReAct | medium | 0.00 | 5.097s | 1.64 | 11.32 | 35.00 | - | 0.00 | - |
| Tool | none | 0.72 | 3.283s | 0.92 | **0.00** | **12.16** | **0.92** | - | - |
| Tool | low | 0.72 | **3.028s** | 0.92 | 8.60 | 21.28 | **0.92** | - | - |
| Tool | medium | **0.76** | 3.047s | 0.96 | 9.56 | 21.96 | **0.92** | - | - |
| Verify | none | **0.80** | 5.098s | 1.96 | **0.00** | 19.64 | - | - | **0.80** |
| Verify | low | **0.80** | **4.515s** | **1.92** | 0.00 | **19.24** | - | - | **0.80** |
| Verify | medium | **0.80** | 5.411s | 1.96 | 1.08 | 21.56 | - | - | **0.80** |

---

# 3. 주요 결과

## 3.1 Reasoning effort를 높인다고 항상 성능이 좋아지지는 않았다

가장 명확한 결과는 `medium reasoning`이 모든 agentic task에서 유리하지 않았다는 점이다.

특히 `verify`에서는:

| Effort | Success | Recovery | Latency |
|---|---:|---:|---:|
| none | 0.80 | 0.80 | 5.098s |
| **low** | **0.80** | **0.80** | **4.515s** |
| medium | 0.80 | 0.80 | 5.411s |

세 설정의 성능이 완전히 동일하다.

그러나 latency는 `low`가 가장 낮다.

따라서 verification처럼 비교적 명확한 판단 task에서는 reasoning effort를 높여도 추가적인 성능 향상이 나타나지 않았으며, 오히려 latency와 token overhead만 증가할 가능성이 있다.

**현재 결과에서는 `low`가 가장 효율적이다.**

---

## 3.2 Tool selection에서도 reasoning의 효과는 매우 작았다

Tool task의 결과:

| Effort | Success | Tool Accuracy | Latency |
|---|---:|---:|---:|
| none | 0.72 | **0.92** | 3.283s |
| low | 0.72 | **0.92** | **3.028s** |
| medium | **0.76** | **0.92** | 3.047s |

`tool_accuracy`는 세 설정 모두 **0.92로 동일**하다.

즉 reasoning을 추가한다고 해서 **어떤 tool을 선택할지 판단하는 능력 자체는 개선되지 않았다.**

`medium`에서 success가 `0.72 → 0.76`으로 4%p 증가했지만, 각 설정의 샘플이 25개이므로 이는 실제로는 **1개 sample 차이**에 해당한다.

따라서 현재 규모의 실험만으로는 medium reasoning이 tool task 성능을 의미 있게 개선했다고 보기 어렵다.

오히려:

- `none`: reasoning token 0
- `low`: 8.6
- `medium`: 9.56

으로 reasoning overhead가 발생한다.

### 해석

간단한 tool routing은 모델 입장에서 비교적 쉬운 classification 문제에 가까우므로, 추가 reasoning이 크게 필요하지 않을 가능성이 높다.

현재 결과만 보면 **`none ~ low`가 충분하다.**

---

# 4. Plan에서는 reasoning 비용이 크게 증가했다

Plan task에서 reasoning effort가 증가하면서 계산량이 매우 명확하게 증가하였다.

| Effort | Latency | Reasoning Tokens | Output Tokens | Tool Calls |
|---|---:|---:|---:|---:|
| none | **3.844s** | **0** | **41.48** | **1.84** |
| low | 5.663s | 52.52 | 96.88 | 2.24 |
| medium | 7.119s | 91.32 | 133.92 | 2.48 |

`none → medium`으로 변경하면:

- latency: `3.844 → 7.119s` (**약 +85%**)
- reasoning tokens: `0 → 91.32`
- output tokens: `41.48 → 133.92` (**약 3.2배**)
- tool calls: `1.84 → 2.48`

즉 planning에서는 reasoning level이 높아질수록 실제로 더 많은 intermediate computation과 action을 수행하는 현상이 명확하게 나타났다.

이는 reasoning effort 설정이 제대로 동작하고 있다는 신호이기도 하다.

하지만 현재 모든 설정에서 `success=0`이므로 **성능과 비용 사이의 trade-off는 아직 판단할 수 없다.**

---

# 5. Plan / ReAct의 success=0은 먼저 evaluator를 점검해야 한다

이번 실험에서 가장 중요한 이상 현상은 다음이다.

```text
Plan
none   success = 0
low    success = 0
medium success = 0

ReAct
none   success = 0
low    success = 0
medium success = 0
```

특히 ReAct에서는:

```text
trajectory_recall = 0
```

이 모든 설정에서 동일하게 발생한다.

Reasoning level과 관계없이 **25/25 sample이 모두 실패**했기 때문에, 이것을 단순히 모델 reasoning 성능 문제로 해석하기는 어렵다.

먼저 다음을 점검할 필요가 있다.

1. trajectory parser가 실제 model output을 정상적으로 parsing하는지
2. expected tool/action 이름과 generated tool/action 이름이 정확히 일치하는지
3. success 조건이 지나치게 strict하지 않은지
4. JSON/schema mismatch가 발생하고 있지 않은지
5. valid trajectory인데 evaluator가 실패로 처리하는 case가 있는지
6. ReAct agent가 실제로 두 번째 step까지 진행하고 있는지

특히 ReAct의 평균 tool call을 보면:

```text
none   1.00
low    1.00
medium 1.64
```

`none`과 `low`가 거의 항상 tool을 한 번만 호출하고 종료하고 있다.

멀티-step ReAct benchmark를 의도했다면 agent loop 자체가 예상보다 일찍 종료되고 있을 가능성도 확인할 필요가 있다.

---

# 6. Reasoning token 사용량도 task마다 크게 달랐다

흥미로운 점은 reasoning effort를 `low` 또는 `medium`으로 설정했다고 해서 항상 reasoning token이 발생하는 것은 아니라는 것이다.

예:

```text
ReAct low      reasoning_tokens = 0.00
Verify low     reasoning_tokens = 0.00
Verify medium  reasoning_tokens = 1.08
```

반면 Plan에서는:

```text
Plan low       = 52.52
Plan medium    = 91.32
```

으로 매우 크게 증가했다.

즉 reasoning effort는 고정된 token budget을 항상 소비하는 것이 아니라 **task difficulty / model 판단에 따라 실제 reasoning 사용량이 달라지는 형태**로 보인다.

따라서 서비스에서는 단순히

```text
medium > low > none
```

의 고정 비용 구조로 가정하기보다 실제 task별 reasoning token 분포를 측정하는 것이 중요하다.

---

# 7. Task별 현재 권장 설정

현재 결과만 기준으로 하면 다음과 같다.

| Task | 추천 | 이유 |
|---|---|---|
| Tool routing | **none / low** | Tool accuracy가 모두 0.92로 동일 |
| Verification | **low** | 동일한 success/recovery에서 latency 최소 |
| Planning | **판단 보류** | reasoning 비용 차이는 명확하지만 success evaluator 문제 |
| ReAct | **판단 보류** | trajectory recall이 모두 0이라 정상 비교 불가능 |

즉 현재 결과는 **모든 agentic step을 일괄적으로 medium reasoning으로 설정할 근거가 없다.**

오히려 task별로 reasoning policy를 다르게 가져가는 것이 합리적이다.

예를 들면:

```python
reasoning_policy = {
    "tool_selection": "none",
    "verification": "low",
    "planning": "medium",   # evaluator 수정 후 재평가
    "react": "low",         # evaluator 수정 후 재평가
}
```

최종 설정은 plan/react evaluator를 수정한 이후 다시 결정해야 한다.

---

# 8. 핵심 결론

이번 실험에서는 **reasoning effort의 효과가 agentic task 종류에 따라 크게 달랐다.**

### Tool Selection

```text
Tool Accuracy
none   = 0.92
low    = 0.92
medium = 0.92
```

Reasoning을 증가시켜도 tool 선택 정확도는 개선되지 않았다.

### Verification

```text
Success / Recovery
none   = 0.80 / 0.80
low    = 0.80 / 0.80
medium = 0.80 / 0.80
```

성능 차이가 없으며 `low`가 가장 빠르다.

### Planning

Reasoning effort를 증가시키면 reasoning token, output token, tool call 및 latency가 모두 크게 증가한다.

특히 medium은 none 대비 약 **85% 높은 latency**를 보였다.

다만 현재 success가 모두 0이므로 실제 품질 향상 여부는 확인할 수 없다.

### ReAct

모든 설정의 trajectory recall과 success가 0으로 측정되었다.

모델 성능 비교 이전에 **agent loop 및 trajectory evaluator 검증이 우선 필요하다.**

---

# 9. 최종 해석

현재 결과는 agent 전체에 하나의 reasoning level을 적용하기보다는 **각 agentic step의 난이도에 따라 reasoning effort를 선택하는 방식**이 더 적절함을 보여준다.

```text
Simple routing / classification
        ↓
      none

Simple verification
        ↓
       low

Complex planning
        ↓
   low / medium

Difficult multi-step trajectory
        ↓
   adaptive reasoning
```

특히 쉬운 task에서는 reasoning을 추가해도 성능 개선 없이 latency와 token 사용량만 증가할 수 있다.

따라서 실제 Agent system에서는 다음 형태가 가장 합리적인 방향이다.

```text
User Query
    ↓
Task / Difficulty Estimation
    ↓
┌─────────────────────────────┐
│ Simple Tool Routing → none  │
│ Verification        → low   │
│ Complex Planning    → med   │
│ Hard Recovery       → med   │
└─────────────────────────────┘
    ↓
Execution
```

즉 **reasoning effort 자체도 routing 대상**으로 볼 수 있다.

---

## Conclusion

> **Reasoning effort should be selected per agentic task rather than globally fixed.**

이번 실험에서는 Tool Selection과 Verification에서 higher reasoning effort가 뚜렷한 성능 향상을 만들지 못했다.

반면 Planning에서는 reasoning level 증가에 따라 계산량과 latency가 크게 증가했다.

따라서 향후에는:

1. Plan/ReAct evaluator 및 trajectory loop를 먼저 수정하고
2. task별 `none / low / medium` 성능을 재평가한 뒤
3. **quality-latency frontier**를 기준으로 reasoning policy를 결정하는 것이 적절하다.

현재 결과만 보면 **“전부 medium”보다는 “쉬운 step은 none/low, 어려운 step만 medium”이라는 selective reasoning 전략이 더 유망하다.**
