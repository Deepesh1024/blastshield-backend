# Implementation Plan: BlastShield

## Overview

This implementation plan breaks down the BlastShield system into incremental, testable steps. The approach follows a bottom-up strategy: build core analysis components first, add AI augmentation, then integrate with external systems. Each task builds on previous work, ensuring no orphaned code.

The implementation uses Python for the core backend, with TypeScript for the VS Code extension.

## Tasks

- [ ] 1. Set up project structure and core infrastructure
  - Create Python project with virtual environment
  - Set up directory structure (src/, tests/, config/)
  - Configure pytest and hypothesis for testing
  - Create core data models (ScanResult, FunctionNode, RiskPattern, etc.)
  - Set up logging configuration
  - _Requirements: All requirements (foundational)_

- [ ] 2. Implement Repository Scanner
  - [ ] 2.1 Implement repository cloning and file filtering
    - Use gitpython to clone repositories
    - Filter files by extension (.py, .js, .ts, .go)
    - Exclude common directories (node_modules, venv, .git)
    - Implement size limit validation
    - _Requirements: 1.1, 1.2_
  
  - [ ]* 2.2 Write property test for scanning completeness
    - **Property 1: Repository Scanning Completeness**
    - **Validates: Requirements 1.1, 1.2, 1.4**
  
  - [ ] 2.3 Implement local workspace scanning
    - Scan local directory without cloning
    - Support for VS Code extension use case
    - _Requirements: 1.1, 9.6_
  
  - [ ]* 2.4 Write property test for parsing error resilience
    - **Property 2: Parsing Error Resilience**
    - **Validates: Requirements 1.3, 15.2**

- [ ] 3. Implement Multi-Language Parser
  - [ ] 3.1 Implement Python parser using ast module
    - Parse Python files to AST
    - Extract function definitions and calls
    - Handle parse errors gracefully
    - _Requirements: 1.2, 1.3_
  
  - [ ] 3.2 Implement JavaScript/TypeScript parser
    - Use @babel/parser or typescript compiler API via subprocess
    - Normalize AST structure to match Python format
    - _Requirements: 1.2_
  
  - [ ] 3.3 Implement Go parser
    - Use go/parser via subprocess
    - Normalize AST structure
    - _Requirements: 1.2_
  
  - [ ] 3.4 Create unified parser interface
    - MultiLanguageParser class that delegates to language-specific parsers
    - Return consistent AST structure across languages
    - _Requirements: 1.4_
  
  - [ ]* 3.5 Write unit tests for each language parser
    - Test valid code parsing
    - Test error handling for invalid syntax
    - _Requirements: 1.2, 1.3_

- [ ] 4. Checkpoint - Ensure parsing tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Execution Graph Builder
  - [ ] 5.1 Create ExecutionGraph and FunctionNode classes
    - Use NetworkX for graph data structure
    - Implement node and edge creation
    - Add metadata storage (async, resource access)
    - _Requirements: 2.1, 2.2_
  
  - [ ] 5.2 Implement function definition extraction
    - Extract all function/method definitions from ASTs
    - Create FunctionNode for each definition
    - Store file location and signature
    - _Requirements: 2.2_
  
  - [ ] 5.3 Implement call site detection
    - Identify all function calls in ASTs
    - Create directed edges in graph
    - Mark async functions with metadata
    - _Requirements: 2.3, 2.4_
  
  - [ ] 5.4 Implement graph query methods
    - get_function_node, get_callers, get_callees
    - traverse_from for depth-first traversal
    - _Requirements: 2.5_
  
  - [ ]* 5.5 Write property test for execution graph completeness
    - **Property 3: Execution Graph Completeness**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
  
  - [ ]* 5.6 Write property test for graph query consistency
    - **Property 4: Graph Query Consistency**
    - **Validates: Requirements 2.5**

- [ ] 6. Implement Risk Detector
  - [ ] 6.1 Create RiskDetector class and rule engine framework
    - Base class for risk detection rules
    - Rule registration and execution system
    - _Requirements: 3.7_
  
  - [ ] 6.2 Implement async misuse detection rule
    - Detect async functions called without await
    - Detect blocking operations in async functions
    - _Requirements: 3.1_
  
  - [ ] 6.3 Implement race condition detection rule
    - Detect shared state access without synchronization
    - Detect check-then-act patterns
    - _Requirements: 3.2_
  
  - [ ] 6.4 Implement idempotency issue detection rule
    - Detect HTTP operations without idempotency keys
    - Detect database operations without uniqueness constraints
    - _Requirements: 3.3_
  
  - [ ] 6.5 Implement resource leak detection rule
    - Detect unclosed files/connections
    - Detect missing context managers
    - _Requirements: 3.4_
  
  - [ ] 6.6 Implement partial transaction detection rule
    - Detect multiple DB operations without transaction wrapper
    - Detect missing rollback in error handlers
    - _Requirements: 3.5_
  
  - [ ]* 6.7 Write property test for risk pattern detection coverage
    - **Property 5: Risk Pattern Detection Coverage**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
  
  - [ ]* 6.8 Write property test for risk detection output structure
    - **Property 6: Risk Detection Output Structure**
    - **Validates: Requirements 3.6**
  
  - [ ]* 6.9 Write property test for deterministic analysis
    - **Property 7: Deterministic Analysis**
    - **Validates: Requirements 3.7, 4.1, 4.4, 12.1, 12.2, 12.3**

- [ ] 7. Checkpoint - Ensure risk detection tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement Risk Scorer
  - [ ] 8.1 Create RiskScorer class with scoring algorithm
    - Implement base weight × confidence × impact formula
    - Load weights from configuration file
    - _Requirements: 4.1, 4.2_
  
  - [ ] 8.2 Implement aggregate score computation
    - Sum individual pattern scores
    - Map to severity levels (Low, Medium, High, Critical)
    - _Requirements: 4.3, 4.5_
  
  - [ ]* 8.3 Write property test for risk score ordering
    - **Property 8: Risk Score Ordering**
    - **Validates: Requirements 4.2**
  
  - [ ]* 8.4 Write property test for aggregate score computation
    - **Property 9: Aggregate Score Computation**
    - **Validates: Requirements 4.3, 4.5**

- [ ] 9. Implement Report Generator
  - [ ] 9.1 Create ReportGenerator class
    - Generate JSON report structure
    - Generate Markdown report structure
    - _Requirements: 5.1, 5.6, 5.7_
  
  - [ ] 9.2 Implement report content generation
    - Include risk score breakdown by pattern type
    - Include failure mode descriptions
    - Include patch recommendations
    - _Requirements: 5.2, 5.3, 5.5_
  
  - [ ]* 9.3 Write property test for report completeness
    - **Property 10: Report Completeness**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5**
  
  - [ ]* 9.4 Write property test for report serialization round-trip
    - **Property 11: Report Serialization Round-Trip**
    - **Validates: Requirements 5.6**
  
  - [ ]* 9.5 Write property test for Markdown report validity
    - **Property 12: Markdown Report Validity**
    - **Validates: Requirements 5.7**

- [ ] 10. Implement AI Explainer
  - [ ] 10.1 Set up AWS Bedrock client
    - Configure boto3 for Bedrock access
    - Implement authentication with AWS credentials
    - _Requirements: 6.1_
  
  - [ ] 10.2 Implement AIExplainer class
    - Create prompt templates for each risk pattern type
    - Call Bedrock API with Claude 3 Sonnet
    - Parse and structure responses
    - Implement caching by pattern type + code hash
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  
  - [ ] 10.3 Implement fallback template explanations
    - Create template explanations for when AI is unavailable
    - Graceful degradation strategy
    - _Requirements: 6.1_
  
  - [ ]* 10.4 Write property test for AI explanation generation
    - **Property 13: AI Explanation Generation**
    - **Validates: Requirements 6.1**
  
  - [ ]* 10.5 Write unit tests for explanation quality
    - Test that explanations contain key terms
    - Test fallback behavior when AI unavailable
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 11. Implement Patch Generator
  - [ ] 11.1 Create PatchGenerator class
    - Create prompt templates for patch generation
    - Call Bedrock API for patch generation
    - Validate patch syntax before returning
    - _Requirements: 7.1, 7.2, 7.3_
  
  - [ ] 11.2 Implement patch formatting
    - Format patches as unified diff
    - Add confidence scores
    - _Requirements: 7.5_
  
  - [ ] 11.3 Implement fallback manual guidance
    - Provide manual remediation guidance when auto-patch fails
    - _Requirements: 7.4_
  
  - [ ]* 11.4 Write property test for patch format validity
    - **Property 14: Patch Format Validity**
    - **Validates: Requirements 7.1, 7.5**
  
  - [ ]* 11.5 Write property test for fallback guidance provision
    - **Property 15: Fallback Guidance Provision**
    - **Validates: Requirements 7.4**

- [ ] 12. Checkpoint - Ensure AI components work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Implement core analysis pipeline
  - [ ] 13.1 Create AnalysisPipeline orchestrator class
    - Wire together: Scanner → Parser → Graph Builder → Risk Detector → Scorer
    - Add AI Explainer and Patch Generator
    - Feed results to Report Generator
    - _Requirements: All core requirements_
  
  - [ ] 13.2 Implement error handling and logging
    - Graceful degradation for partial failures
    - Structured error responses
    - Privacy-preserving logging (no source code in logs)
    - _Requirements: 15.1, 15.2, 15.3, 14.5_
  
  - [ ]* 13.3 Write property test for log privacy
    - **Property 24: Log Privacy**
    - **Validates: Requirements 14.5**
  
  - [ ]* 13.4 Write property test for error message quality
    - **Property 25: Error Message Quality**
    - **Validates: Requirements 15.1, 15.2, 15.3**
  
  - [ ]* 13.5 Write integration tests for full pipeline
    - Test end-to-end analysis flow
    - Test with sample repositories
    - _Requirements: All core requirements_

- [ ] 14. Implement database layer
  - [ ] 14.1 Set up PostgreSQL schema
    - Create tables: scans, patterns, users, repositories
    - Set up indexes for performance
    - _Requirements: 11.1_
  
  - [ ] 14.2 Implement database models with SQLAlchemy
    - Create ORM models for all tables
    - Implement CRUD operations
    - _Requirements: 11.1_
  
  - [ ] 14.3 Implement risk history storage
    - Store scan results and timestamps
    - Implement history retrieval queries
    - _Requirements: 11.1, 11.5_
  
  - [ ]* 14.4 Write property test for risk history persistence
    - **Property 22: Risk History Persistence**
    - **Validates: Requirements 11.1**
  
  - [ ]* 14.5 Write property test for risk history comparison
    - **Property 23: Risk History Comparison**
    - **Validates: Requirements 11.3, 11.4**

- [ ] 15. Implement caching layer
  - [ ] 15.1 Set up Redis client
    - Configure redis-py client
    - Implement connection pooling
    - _Requirements: 13.1_
  
  - [ ] 15.2 Implement execution graph caching
    - Cache graphs by repository + commit hash
    - Implement TTL for cache entries
    - _Requirements: 13.1_
  
  - [ ] 15.3 Implement explanation caching
    - Cache AI explanations by pattern type + code hash
    - Reduce AI API calls for similar patterns
    - _Requirements: 6.5_

- [ ] 16. Implement REST API
  - [ ] 16.1 Set up FastAPI application
    - Create FastAPI app with routes
    - Configure CORS and middleware
    - _Requirements: 8.1, 9.1, 10.1_
  
  - [ ] 16.2 Implement scan endpoints
    - POST /api/scans - Initiate new scan
    - GET /api/scans/{scan_id} - Get scan results
    - GET /api/scans/{scan_id}/report - Get formatted report
    - _Requirements: 8.1, 9.1, 10.1_
  
  - [ ] 16.3 Implement history endpoints
    - GET /api/repositories/{repo_id}/history - Get risk history
    - GET /api/repositories/{repo_id}/compare - Compare two scans
    - _Requirements: 11.2, 11.3, 11.4_
  
  - [ ] 16.4 Implement authentication
    - OAuth 2.0 integration for user authentication
    - JWT token generation and validation
    - _Requirements: 14.4_
  
  - [ ] 16.5 Implement rate limiting
    - Rate limit demo endpoint (10 scans per IP per hour)
    - Rate limit by user tier for authenticated users
    - _Requirements: 10.5_
  
  - [ ]* 16.6 Write property test for demo rate limiting
    - **Property 21: Demo Rate Limiting**
    - **Validates: Requirements 10.5**
  
  - [ ]* 16.7 Write integration tests for API endpoints
    - Test all endpoints with various inputs
    - Test authentication and authorization
    - _Requirements: 8.1, 9.1, 10.1, 11.2, 14.4_

- [ ] 17. Checkpoint - Ensure API tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. Implement GitHub Integration
  - [ ] 18.1 Set up GitHub App
    - Register GitHub App with webhook permissions
    - Configure webhook URL and secret
    - _Requirements: 8.1, 8.6_
  
  - [ ] 18.2 Implement webhook handler
    - Handle pull_request.opened events
    - Handle pull_request.synchronize events
    - Trigger scans on PR events
    - _Requirements: 8.1, 8.5_
  
  - [ ] 18.3 Implement PR comment posting
    - Post Blast Report as PR comment
    - Format report for GitHub Markdown
    - _Requirements: 8.2_
  
  - [ ] 18.4 Implement PR status checks
    - Set status to failure for high/critical risks
    - Set status to success with warnings for low/medium risks
    - _Requirements: 8.3, 8.4_
  
  - [ ]* 18.5 Write property test for GitHub PR status logic
    - **Property 16: GitHub PR Status Logic**
    - **Validates: Requirements 8.3, 8.4**
  
  - [ ]* 18.6 Write integration tests for GitHub webhook handling
    - Mock GitHub webhook events
    - Test PR comment posting
    - Test status check updates
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 19. Implement Web Demo Interface
  - [ ] 19.1 Create web frontend with React
    - Create simple UI for repository URL input
    - Display scan progress and results
    - _Requirements: 10.1, 10.3_
  
  - [ ] 19.2 Implement demo-specific validation
    - Validate repository size limit (5,000 LOC)
    - Implement rate limiting UI feedback
    - _Requirements: 10.4, 10.5_
  
  - [ ] 19.3 Implement temporary storage cleanup
    - Schedule S3 cleanup job for repositories older than 1 hour
    - _Requirements: 10.6_
  
  - [ ]* 19.4 Write property test for demo size validation
    - **Property 20: Demo Size Validation**
    - **Validates: Requirements 10.2, 10.4**
  
  - [ ]* 19.5 Write integration tests for web demo
    - Test repository submission flow
    - Test size limit enforcement
    - Test rate limiting
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 20. Implement VS Code Extension
  - [ ] 20.1 Set up VS Code extension project (TypeScript)
    - Create extension manifest (package.json)
    - Set up TypeScript build configuration
    - _Requirements: 9.1_
  
  - [ ] 20.2 Implement scan command
    - Register "BlastShield: Scan Workspace" command
    - Trigger local analysis on current workspace
    - _Requirements: 9.1_
  
  - [ ] 20.3 Implement progress UI
    - Display scan progress in status bar
    - Show notifications for scan completion
    - _Requirements: 9.2_
  
  - [ ] 20.4 Implement Problems panel integration
    - Convert detected risks to VS Code diagnostics
    - Display in Problems panel with correct locations
    - _Requirements: 9.3_
  
  - [ ] 20.5 Implement quick fix actions
    - Provide code actions for risks with patches
    - Apply patches when user accepts quick fix
    - _Requirements: 9.5_
  
  - [ ] 20.6 Implement offline analysis
    - Bundle Python analysis engine with extension
    - Run analysis locally without network calls
    - _Requirements: 9.6_
  
  - [ ]* 20.7 Write property test for Problems panel integration
    - **Property 17: VS Code Problems Panel Integration**
    - **Validates: Requirements 9.3**
  
  - [ ]* 20.8 Write property test for quick fix availability
    - **Property 18: VS Code Quick Fix Availability**
    - **Validates: Requirements 9.5**
  
  - [ ]* 20.9 Write property test for offline analysis support
    - **Property 19: Offline Analysis Support**
    - **Validates: Requirements 9.6**

- [ ] 21. Implement deployment infrastructure
  - [ ] 21.1 Create Dockerfile for API service
    - Multi-stage build for Python application
    - Include all language parsers (Python, Node.js, Go)
    - _Requirements: 13.1_
  
  - [ ] 21.2 Create AWS infrastructure with Terraform
    - ECS Fargate cluster for API and workers
    - RDS PostgreSQL database
    - ElastiCache Redis cluster
    - S3 bucket for temporary storage
    - Application Load Balancer
    - _Requirements: 13.1, 13.3, 13.5_
  
  - [ ] 21.3 Configure auto-scaling
    - Scale based on queue depth and CPU utilization
    - Configure min/max instance counts
    - _Requirements: 13.5_
  
  - [ ] 21.4 Set up monitoring and alerting
    - CloudWatch dashboards for key metrics
    - Alarms for error rates and latency
    - _Requirements: 15.5_
  
  - [ ] 21.5 Configure security
    - TLS termination at load balancer
    - Encryption at rest for RDS and S3
    - Secrets Manager for credentials
    - _Requirements: 14.1, 14.2, 14.3_

- [ ] 22. Final checkpoint - End-to-end testing
  - [ ] 22.1 Run full test suite
    - All unit tests pass
    - All property tests pass (100 iterations)
    - All integration tests pass
    - _Requirements: All requirements_
  
  - [ ] 22.2 Perform manual testing
    - Test GitHub integration with real PR
    - Test VS Code extension with real workspace
    - Test web demo with sample repositories
    - _Requirements: 8.1, 9.1, 10.1_
  
  - [ ] 22.3 Validate performance requirements
    - Test 10k LOC repository completes in <15 seconds
    - Test 50k LOC repository completes in <60 seconds
    - _Requirements: 13.1, 13.2_
  
  - [ ] 22.4 Validate security requirements
    - Verify TLS encryption
    - Verify data encryption at rest
    - Verify OAuth authentication
    - Verify no source code in logs
    - _Requirements: 14.1, 14.2, 14.4, 14.5_

- [ ] 23. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (minimum 100 iterations each)
- Unit tests validate specific examples and edge cases
- The implementation follows a bottom-up approach: core components first, then integrations
- Python is used for the backend, TypeScript for the VS Code extension
- AWS services (Bedrock, ECS, RDS, ElastiCache, S3) are used for deployment
