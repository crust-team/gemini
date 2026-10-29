# Contributing

Use Python 3.11 and install development dependencies with `poetry install`. Read
[AGENTS.md](AGENTS.md) and its linked conventions before changing equipment or physics.
Run the validation commands in [README.md](README.md) before submitting changes.

# Development guidelines
The general proces is as follows:
* Create a branch on your local working copy
* make code modifications, including tests, documentation, etc
* commit/push changes to remote/origin
* submit a pull request for merging into master
* Discuss with code reviewer if/what changes are needed
* when all discussions are resolved, the PR will be merged by the reviewer
* Update Changelog!


# Code Quality guide lines
Quality guide lines serve to improve quality. They should not be busy work nor work against developers.
They should be of value.

## Code review
- Every commit should be created on its own branch and submitted per pull request to be merged with the main branch.
- Every pull request must be reviewed by at least one other developer and all comments must be resolved.
- No linting issues may remain before merging.
- Code reviews are not about distrust. They are about sharing knowledge about the code base, sharing knowledge about
  writing code and increasing quality by collaboration.

## Documentation
- Every function must have documentation explaining what the function does in a summary and explaining
  each argument and return type.

## Linting
- Linting maintains a shared quality of the code base across repositories.
- Rules of the linter may only be ignored when approved by the software leads. Prefer to silence individual lines by <TODO show how to silence individual errors>'

## Testing

Run `pytest` for the fast tier while developing. Before merging, run
`pytest -n auto -m "" --dataset=slow`; feature CI also runs
`pytest -n auto -m "e2e or slow" --dataset=fast`. The tier markers, one-second test budget,
shared fixtures, datasets and golden workflow are defined in
[.claude/docs/testing.md](.claude/docs/testing.md).

### Unit testing
- Every function should be covered by a unit test. Some functions allow more easily for unit tests and some are not
  worth unit testing. This is up to the teams discretion.
- A unit test should test some significant amount of code. If the test function is similar or equal to the logic being tested,
the amount of code being tested is too small. If the test function tests whole modules or multiple layers of code, the amount
of code being tested is too big. The amount of code being tested is referred to as the 'unit-under-test'.
- Use mocks to isolate 'unit-under-test' where applicable.
- Coverage percentage should be >80%. This is a guideline, not a hard rule. Breaking this guideline is allowed if the 
  arguments has swayed the developers team and not just the developer and reviewer.
