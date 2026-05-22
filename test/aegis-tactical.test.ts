import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { FoundationStack } from '../lib/foundation-stack';
import { LambdaStack } from '../lib/lambda-stack';
import { GuardrailsStack } from '../lib/guardrails-stack';

describe('Aegis-Tactical CDK Stacks', () => {
  let app: cdk.App;

  beforeEach(() => {
    app = new cdk.App();
  });

  // ─── Foundation Stack Tests ───────────────────────────────────────────

  describe('FoundationStack', () => {
    let template: Template;

    beforeEach(() => {
      const stack = new FoundationStack(app, 'TestFoundationStack', {
        env: { account: '123456789012', region: 'us-east-1' },
      });
      template = Template.fromStack(stack);
    });

    test('creates S3 bucket with encryption', () => {
      template.hasResourceProperties('AWS::S3::Bucket', {
        BucketEncryption: {
          ServerSideEncryptionConfiguration: [
            {
              ServerSideEncryptionByDefault: {
                SSEAlgorithm: 'AES256',
              },
            },
          ],
        },
      });
    });

    test('creates OpenSearch Serverless collection', () => {
      template.hasResourceProperties('AWS::OpenSearchServerless::Collection', {
        Name: 'aegis-vectors',
        Type: 'VECTORSEARCH',
      });
    });

    test('creates Bedrock Knowledge Base', () => {
      template.hasResourceProperties('AWS::Bedrock::KnowledgeBase', {
        Name: 'aegis-tactical-kb',
      });
    });

    test('creates encryption and network policies', () => {
      template.resourceCountIs('AWS::OpenSearchServerless::SecurityPolicy', 2);
    });

    test('creates S3 data source', () => {
      template.hasResourceProperties('AWS::Bedrock::DataSource', {
        Name: 'aegis-ground-truth-source',
      });
    });

    test('creates IAM role for Knowledge Base', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'AegisKnowledgeBaseRole',
      });
    });
  });

  // ─── Lambda Stack Tests ───────────────────────────────────────────────

  describe('LambdaStack', () => {
    let template: Template;

    beforeEach(() => {
      const foundation = new FoundationStack(app, 'TestFoundation', {
        env: { account: '123456789012', region: 'us-east-1' },
      });
      const stack = new LambdaStack(app, 'TestLambdaStack', {
        env: { account: '123456789012', region: 'us-east-1' },
        groundTruthBucket: foundation.groundTruthBucket,
      });
      template = Template.fromStack(stack);
    });

    test('creates 4 Lambda functions', () => {
      template.resourceCountIs('AWS::Lambda::Function', 4);
    });

    test('uses Python 3.12 runtime', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        Runtime: 'python3.12',
      });
    });

    test('creates fetch_news function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'aegis-fetch-news',
      });
    });

    test('creates fetch_rss function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'aegis-fetch-rss',
      });
    });

    test('creates fetch_github function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'aegis-fetch-github',
      });
    });

    test('creates write_report function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'aegis-write-report',
      });
    });

    test('sets correct timeout', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        Timeout: 30,
      });
    });
  });

  // ─── Guardrails Stack Tests ───────────────────────────────────────────

  describe('GuardrailsStack', () => {
    let template: Template;

    beforeEach(() => {
      const stack = new GuardrailsStack(app, 'TestGuardrailsStack', {
        env: { account: '123456789012', region: 'us-east-1' },
      });
      template = Template.fromStack(stack);
    });

    test('creates Bedrock Guardrail', () => {
      template.hasResourceProperties('AWS::Bedrock::Guardrail', {
        Name: 'aegis-defense-guardrail',
      });
    });

    test('creates Guardrail version', () => {
      template.resourceCountIs('AWS::Bedrock::GuardrailVersion', 1);
    });

    test('configures content policy filters', () => {
      template.hasResourceProperties('AWS::Bedrock::Guardrail', {
        ContentPolicyConfig: {
          FiltersConfig: Match.arrayWith([
            Match.objectLike({ Type: 'HATE', InputStrength: 'HIGH' }),
            Match.objectLike({ Type: 'PROMPT_ATTACK', InputStrength: 'HIGH' }),
          ]),
        },
      });
    });

    test('configures denied topics', () => {
      template.hasResourceProperties('AWS::Bedrock::Guardrail', {
        TopicPolicyConfig: {
          TopicsConfig: Match.arrayWith([
            Match.objectLike({ Name: 'DestructiveOperations', Type: 'DENY' }),
          ]),
        },
      });
    });

    test('configures PII filters', () => {
      template.hasResourceProperties('AWS::Bedrock::Guardrail', {
        SensitiveInformationPolicyConfig: {
          PiiEntitiesConfig: Match.arrayWith([
            Match.objectLike({ Type: 'US_SOCIAL_SECURITY_NUMBER', Action: 'BLOCK' }),
          ]),
        },
      });
    });
  });
});
