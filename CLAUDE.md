# Development Guidelines for Claude

## Core Development Principles

### 1. Single Responsibility Principle (SRP)

- Each class and function should have exactly one reason to change
- If a function does multiple things, split it into smaller, focused functions
- Always ask: "What is this component's single job?"

### 2. Don't Repeat Yourself (DRY)

- Extract common patterns into reusable utilities
- Create shared base classes for similar functionality
- Use configuration-driven approaches instead of hardcoded values
- If you write the same logic twice, create a shared function

### 3. Testability First

- Design every component to be easily unit testable in isolation
- Use dependency injection for external dependencies
- Create clear interfaces that can be mocked
- Write testable code BEFORE writing the actual implementation

## Project Architecture Patterns

### Follow Existing Patterns

- **Workflow Structure**: Use `src/workflows/balance_checker.py` as template for new workflows
- **Google Sheets Integration**: Follow patterns from `src/gsheets/ledger.py`
- **Email Notifications**: Leverage existing `src/resend/` infrastructure
- **Environment Configuration**: Use environment-based configuration approach
- **Error Handling**: Follow patterns from existing modules

### Directory Structure

```
src/
├── ynab/          # YNAB API integration and data models
├── gsheets/       # Google Sheets operations
├── workflows/     # Business logic orchestration
├── resend/        # Email notification system
└── [new_feature]/ # New feature modules
```

## Mandatory Implementation Standards

### Code Structure Requirements

**Every new module MUST include:**

```python
"""
Module docstring explaining purpose and responsibilities.
Follows Single Responsibility Principle - handles X and only X.
"""
from typing import List, Dict, Optional, Protocol
import logging

logger = logging.getLogger(__name__)

# Clear type definitions at the top
# Dependency injection interfaces
# Main implementation classes
# Error handling classes
```

**Every class MUST:**

- Have a clear docstring explaining its single responsibility
- Use type hints for all public methods
- Implement proper error handling with descriptive messages
- Be testable in isolation (accept dependencies via constructor)

**Every function MUST:**

- Have type hints for parameters and return values
- Include docstring with purpose, parameters, and return value
- Be pure functions when possible (no side effects)
- Handle edge cases explicitly

### Testing Requirements

**For every component, Claude MUST create:**

1. **Unit Test File Structure:**

```python
"""
test_[module_name].py

Tests for [ModuleName] following AAA pattern:
- Arrange: Set up test data and mocks
- Act: Execute the function/method being tested
- Assert: Verify expected behavior
"""
import pytest
from unittest.mock import Mock, patch
from src.[feature].[module] import [ClassName]

class Test[ClassName]:
    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Initialize common test data

    def test_[method_name]_success_case(self):
        """Test successful execution with valid inputs."""
        # Arrange
        # Act
        # Assert

    def test_[method_name]_error_case(self):
        """Test error handling with invalid inputs."""
        # Arrange
        # Act & Assert (expecting exception)

    def test_[method_name]_edge_case(self):
        """Test boundary conditions and edge cases."""
        # Arrange
        # Act
        # Assert
```

2. **Test Coverage Requirements:**
   - Happy path scenarios (successful execution)
   - Error cases (invalid inputs, external failures)
   - Edge cases (empty data, boundary values)
   - Integration points (mock external dependencies)

### Dependency Injection Pattern

**Always use this pattern for external dependencies:**

```python
# Define protocol for testability
class ExternalService(Protocol):
    def method_name(self, param: str) -> Dict: ...

class BusinessLogicClass:
    def __init__(
        self,
        external_service: ExternalService,
        config_loader: ConfigLoader,
        logger: logging.Logger = None
    ):
        """Inject all external dependencies for testability."""
        self.external_service = external_service
        self.config_loader = config_loader
        self.logger = logger or logging.getLogger(__name__)
```

### Error Handling Standards

**Use this error handling pattern:**

```python
class [Feature]Error(Exception):
    """Raised when [feature] fails due to business logic issues."""
    pass

class ConfigurationError(Exception):
    """Raised when configuration is invalid."""
    pass

def business_method(self, data: List[SomeType]) -> List[ResultType]:
    """Business logic method with comprehensive error handling."""
    try:
        if not data:
            self.logger.info("No data provided for processing")
            return []

        # Main logic here

    except ConfigurationError as e:
        self.logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        self.logger.error(f"Unexpected error: {e}")
        raise [Feature]Error(f"Failed to process: {e}") from e
```

## Implementation Workflow

**Claude should follow this process for each component:**

1. **Design Phase:**

   - Identify the single responsibility of the component
   - Define clear interfaces using Python protocols
   - Plan dependency injection points
   - Design error handling strategy

2. **Test-First Implementation:**

   - Write comprehensive unit tests first (TDD approach)
   - Include tests for success, error, and edge cases
   - Mock all external dependencies
   - Verify tests fail initially (red phase)

3. **Implementation Phase:**

   - Implement minimal code to make tests pass (green phase)
   - Follow DRY principles - extract common patterns
   - Add comprehensive logging and error handling
   - Ensure type safety with proper type hints

4. **Refactor Phase:**
   - Review for SRP violations - split if necessary
   - Extract reusable utilities
   - Optimize for readability and maintainability
   - Verify all tests still pass

## Quality Assurance Checklist

**Before considering any component complete, verify:**

- [ ] **SRP**: Component has exactly one responsibility
- [ ] **DRY**: No code duplication, common patterns extracted
- [ ] **Testability**: All external dependencies can be mocked
- [ ] **Type Safety**: Complete type hints on all public interfaces
- [ ] **Error Handling**: Comprehensive error handling with descriptive messages
- [ ] **Documentation**: Clear docstrings explaining purpose and usage
- [ ] **Test Coverage**: Tests for success, error, and edge cases
- [ ] **Logging**: Appropriate logging for debugging and monitoring
- [ ] **Configuration**: No hardcoded values, everything configurable

## Integration Testing Strategy

**For end-to-end testing, create integration tests that:**

- Use real external APIs (with test accounts/data)
- Load actual configuration files (test configurations)
- Test complete workflows from start to finish
- Verify external integrations work correctly
- Test failure scenarios and recovery

## Performance Considerations

**Claude should optimize for:**

- Batch external API operations when possible
- Cache configuration data to avoid repeated parsing
- Use appropriate data structures (avoid O(n²) operations)
- Implement proper resource cleanup (close files, cleanup temp data)
- Consider rate limiting for external API calls

## GitHub Actions Integration

**When creating workflows:**

- Follow patterns from existing `.github/workflows/` files
- Use the same Python version (3.11)
- Include proper secret management (no hardcoded credentials)
- Add cleanup steps for temporary files
- Use `workflow_dispatch` for manual triggering
