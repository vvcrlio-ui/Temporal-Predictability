# Temporal FFCWS

## Research Question

This project studies a life-course question: as children grow up, as their observable life history accumulates, and as the data available to researchers grow, to what extent do future outcomes become predictable?

We do not treat a single modeling competition or a single GPA example as the end object of study. The question breaks down as follows:

1. At the end of each developmental stage, how well can future educational, psychological, economic, and family outcomes be predicted?
2. As the number of training families $N$ and the number of predictors $K$ increase jointly, how does predictive performance scale, and when do diminishing marginal returns become evident?
3. Does the improvement from adding an observation wave depend on data scale? In other words, does the information value of a given stage emerge only when there are enough samples and variables?
4. Holding the observation point fixed and pushing the outcome age further out, how does predictability decay? Does information have a "shelf life"?
5. For the same prediction horizon, does predictability differ between an earlier and a later segment of the life course?
6. Do different outcomes behave differently? Do some plateau early while others continue to be shaped by later life experiences?
7. Are the conclusions robust to model type and feature sampling?
8. When the information set is fixed and the training sample grows, where does prediction error level off? Can that limit provide a credible upper bound on the unpredictability of life outcomes?

This project studies predictive structure and upper bounds on unpredictability. It does not interpret these relationships as causal effects.

## Experimental Design

### Data

The data come from the Fragile Families and Child Wellbeing Study (FFCWS), a US birth cohort followed from birth through ages 1, 3, 5, 9, 15, and 22. The age-15 outcomes are those of the Fragile Families Challenge: GPA, grit, material hardship, eviction, caregiver layoff, and job training.

### The Predictability Surface

The main empirical object is **a surface over joint data scale × observation wave × outcome age × out-of-sample predictive performance**, built separately for each outcome construct. The four dimensions are:

- **Joint data scale**: $N$ and $K$ increase together along a pre-specified path, for example from $(N_{\min},K_{\min})$ step by step to $(N_{\max},K_{\max})$. This axis represents the researcher's data resources growing from scarce to abundant; it is not $N$ or $K$ alone.
- **Observation wave** $t$: the model may use only information already observed by a given age. The available cutoffs are birth and ages 1, 3, 5, 9, and 15. Under the cumulative scheme, the information sets are strictly nested by age.
- **Outcome age** $T$: the age at which the predicted outcome is measured, subject to $t < T$. This axis exists only when the same construct is measured repeatedly at several values of $T$.
- **Predictive performance**: out-of-sample error, explained variance, or normalized unpredictability, computed on a predefined test sample.

Let $b$ index the joint scale levels, each corresponding to a pair $(N_b,K_b)$. The surface can be written as:

$$
P_Y(t,T,b)=\mathrm{Performance}\bigl(Y_T\mid H_{\le t},N_b,K_b\bigr).
$$

The surface shows three kinds of change at once. Along the wave direction, the researcher gains more life history. Along the scale direction, the researcher has more families and more variables. Along the outcome-age direction, the predicted event lies further from the observation point. Horizontal, vertical, diagonal (fixed horizon $T-t$), and matched $K$ comparisons are all slice queries on the same surface, not separate experiments.

Because the four axes multiply, the surface is necessarily **sampled** rather than filled in. Every run declares in advance which slices it covers and why.

### Joint Scale Levels

A formal run chooses several ordered scale levels:

```text
Scale level 1   (N1, K1)
Scale level 2   (N2, K2)
...             ...
Scale level B   (Nmax, Kmax)
```

The same set of scale levels is evaluated at every observation wave, forming a regular grid. $N$ and $K$ usually grow together on a log scale so that both the low-data and the high-data regions have enough resolution.

The joint path answers the question "what happens when data resources grow overall?" Because $N$ and $K$ change together, the path by itself cannot tell whether an improvement comes from more families or from more variables.

### Fixed-Condition Diagnostic Slices

To support statistical interpretation, a small number of diagnostic slices are kept alongside the main surface:

- Fix $K$, vary $N$: estimate learning curves, check finite-sample bias, and estimate the asymptotic error when extrapolation is credible.
- Fix $N$, vary $K$: determine whether adding variables still yields incremental value.
- Match $K$ across waves: separate "new life-history information has appeared" from "more variables were simply used". **Comparing along $t$ at each wave's full $K$ describes the overall expansion of the data and cannot substitute for this slice.**
- Fix the construct, vary $T$: all values of $T$ share one analysis sample and one train–test split; otherwise, longitudinal differences cannot be separated from changes in sample composition.

### Composition Experiments

A separate class of experiments changes which pool the variables come from, not the values of $N$, $K$, $t$, or $T$. Examples are using only a wave's own variables (snapshot) and removing one category of items by content (ablation). These experiments lie outside the surface: each is built as its own feature set and reported as a diagnostic, never plotted as an additional unpredictability curve alongside the surface slices.

The joint surface presents the full phenomenon, while the diagnostic slices and composition experiments explain the surface and validate the conclusions. The three are not substitutes for one another.

### From Prediction Error to an Unpredictability Bound

For outcome age $s$, the theoretical target is:

$$
U(t,s)=\frac{\mathbb{E}[\mathrm{Var}(Y_s\mid H_{\le t})]}{\mathrm{Var}(Y_s)}.
$$

$U(t,s)$ is the fraction of the variance of the outcome at age $s$ that remains unpredictable at age $t$, given the life history observed up to that age. As the information set grows, the true $U(t,s)$ should not increase.

With finite data, the observed prediction error contains not only the inherent unpredictability of the outcome but also the effects of too few samples, too few variables, and incomplete model learning. The joint-scale surface therefore cannot be called $U(t,s)$ directly. Only when a learning curve with a fixed information set passes the extrapolation self-check is its asymptotic error reported as an empirical upper bound on $U(t,s)$. Both the raw estimate and the monotonized estimate are retained.

### Stages

**1. Method demo.** Outcome: GPA at age 15. Observation cutoffs: birth and ages 1, 3, 5, and 9. The demo tests whether the wave partition, learning curves at fixed $K$, the asymptote self-check, and figure interpretation work in practice, and supplies the estimation and diagnostic components for the joint surface. It is a method validation, not the research goal.

**2. Age-15 multi-outcome study.** The design extends to all six Challenge outcomes and formally adds the joint scale axis, in which $N$ and $K$ grow together. Each outcome gets its own surface, diagnostic slices, and unpredictability upper bound. Raw errors and $U$ levels are not simply ranked across outcomes, because the outcomes differ in scale and measurement.

**3. Life-course extension.** Outcome age becomes an axis: the same construct is measured at ages 9, 15, and 22, the observation cutoffs extend to age 15, and the analysis covers the full $(t,T)$ grid. Outcome constructs, data availability, attrition, and measurement comparability are checked anew rather than carried over from the demo.

**The outcome-age axis places a hard constraint on constructs**: comparisons across $T$ require the same scale, the same scoring rule, and the same reporter. Among the six Challenge outcomes, only household material hardship meets this requirement (its 11-item battery is worded identically at ages 9, 15, and 22). The other outcomes either exist at a single time point or change construct and reporter across ages. This axis therefore applies to fewer outcomes than the other three axes.
