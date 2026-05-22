import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as opensearch from 'aws-cdk-lib/aws-opensearchserverless';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

/**
 * FoundationStack — Phase 1
 *
 * Provisions the data foundation for Aegis-Tactical:
 *   - S3 bucket for Ground Truth documents
 *   - OpenSearch Serverless collection for vector storage
 *   - Bedrock Knowledge Base wired to S3 + OpenSearch
 *   - Auto-uploads sample ground-truth data on deploy
 */
export class FoundationStack extends cdk.Stack {
  /** The S3 bucket storing verified ground truth documents */
  public readonly groundTruthBucket: s3.Bucket;
  /** The Knowledge Base ID for RAG queries */
  public readonly knowledgeBaseId: string;
  /** The Knowledge Base ARN */
  public readonly knowledgeBaseArn: string;
  /** The OpenSearch collection ARN */
  public readonly collectionArn: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ─── S3 Ground Truth Bucket ───────────────────────────────────────
    this.groundTruthBucket = new s3.Bucket(this, 'GroundTruthBucket', {
      bucketName: `aegis-ground-truth-${this.account}-${this.region}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Auto-upload sample ground truth data on deploy
    new s3deploy.BucketDeployment(this, 'DeployGroundTruth', {
      sources: [s3deploy.Source.asset('./data/ground-truth')],
      destinationBucket: this.groundTruthBucket,
      destinationKeyPrefix: 'documents/',
    });

    // ─── OpenSearch Serverless Collection ─────────────────────────────
    const collectionName = 'aegis-vectors';

    // Encryption policy (required for AOSS)
    const encryptionPolicy = new opensearch.CfnSecurityPolicy(this, 'EncryptionPolicy', {
      name: 'aegis-encryption-policy',
      type: 'encryption',
      policy: JSON.stringify({
        Rules: [
          {
            ResourceType: 'collection',
            Resource: [`collection/${collectionName}`],
          },
        ],
        AWSOwnedKey: true,
      }),
    });

    // Network policy — allow public access for Bedrock service
    const networkPolicy = new opensearch.CfnSecurityPolicy(this, 'NetworkPolicy', {
      name: 'aegis-network-policy',
      type: 'network',
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: 'collection',
              Resource: [`collection/${collectionName}`],
            },
            {
              ResourceType: 'dashboard',
              Resource: [`collection/${collectionName}`],
            },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    // Create the vector collection
    const collection = new opensearch.CfnCollection(this, 'VectorCollection', {
      name: collectionName,
      type: 'VECTORSEARCH',
      description: 'Aegis-Tactical vector store for Knowledge Base embeddings',
    });
    collection.addDependency(encryptionPolicy);
    collection.addDependency(networkPolicy);

    this.collectionArn = collection.attrArn;

    // ─── IAM Role for Bedrock Knowledge Base ──────────────────────────
    const kbRole = new iam.Role(this, 'KnowledgeBaseRole', {
      roleName: 'AegisKnowledgeBaseRole',
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      description: 'IAM role for Aegis-Tactical Bedrock Knowledge Base',
    });

    // Grant access to the S3 bucket
    this.groundTruthBucket.grantRead(kbRole);

    // Grant access to OpenSearch Serverless
    kbRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['aoss:APIAccessAll'],
      resources: [collection.attrArn],
    }));

    // Grant Bedrock model invocation for embeddings
    kbRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['bedrock:InvokeModel'],
      resources: [
        `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
      ],
    }));

    // Data access policy for the Knowledge Base role
    const dataAccessPolicy = new opensearch.CfnAccessPolicy(this, 'DataAccessPolicy', {
      name: 'aegis-data-access-policy',
      type: 'data',
      policy: JSON.stringify([
        {
          Rules: [
            {
              ResourceType: 'index',
              Resource: [`index/${collectionName}/*`],
              Permission: [
                'aoss:CreateIndex',
                'aoss:UpdateIndex',
                'aoss:DescribeIndex',
                'aoss:ReadDocument',
                'aoss:WriteDocument',
              ],
            },
            {
              ResourceType: 'collection',
              Resource: [`collection/${collectionName}`],
              Permission: [
                'aoss:CreateCollectionItems',
                'aoss:DescribeCollectionItems',
                'aoss:UpdateCollectionItems',
              ],
            },
          ],
          Principal: [
            kbRole.roleArn,
            `arn:aws:iam::${this.account}:role/cdk-hnb659fds-cfn-exec-role-${this.account}-${this.region}`,
            `arn:aws:iam::${this.account}:root`,
          ],
        },
      ]),
    });

    // Explicitly create the vector index before Knowledge Base creation.
    // Bedrock expects the index to already exist when binding to OpenSearch Serverless.
    const vectorIndex = new opensearch.CfnIndex(this, 'VectorIndex', {
      collectionEndpoint: collection.attrCollectionEndpoint,
      indexName: 'aegis-vector-index',
      settings: {
        index: {
          knn: true,
        },
      },
      mappings: {
        properties: {
          embedding: {
            type: 'knn_vector',
            dimension: 1024,
            method: {
              engine: 'faiss',
              name: 'hnsw',
              spaceType: 'l2',
            },
          },
          text: {
            type: 'text',
          },
          metadata: {
            type: 'text',
          },
        },
      },
    });
    vectorIndex.cfnOptions.deletionPolicy = cdk.CfnDeletionPolicy.RETAIN;
    vectorIndex.cfnOptions.updateReplacePolicy = cdk.CfnDeletionPolicy.RETAIN;
    vectorIndex.addDependency(collection);
    vectorIndex.addDependency(dataAccessPolicy);

    // ─── Bedrock Knowledge Base ───────────────────────────────────────
    const knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'AegisKnowledgeBase', {
      name: 'aegis-tactical-kb',
      description: 'Ground truth knowledge base for Aegis-Tactical intelligence verification',
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: 'OPENSEARCH_SERVERLESS',
        opensearchServerlessConfiguration: {
          collectionArn: collection.attrArn,
          vectorIndexName: 'aegis-vector-index',
          fieldMapping: {
            vectorField: 'embedding',
            textField: 'text',
            metadataField: 'metadata',
          },
        },
      },
    });
    knowledgeBase.addDependency(dataAccessPolicy);
    knowledgeBase.node.addDependency(kbRole);
    knowledgeBase.addDependency(vectorIndex);

    this.knowledgeBaseId = knowledgeBase.attrKnowledgeBaseId;
    this.knowledgeBaseArn = knowledgeBase.attrKnowledgeBaseArn;

    // ─── Data Source (S3) for Knowledge Base ──────────────────────────
    new bedrock.CfnDataSource(this, 'GroundTruthDataSource', {
      name: 'aegis-ground-truth-source',
      knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: {
          bucketArn: this.groundTruthBucket.bucketArn,
          inclusionPrefixes: ['documents/'],
        },
      },
    });

    // ─── Outputs ──────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'GroundTruthBucketName', {
      value: this.groundTruthBucket.bucketName,
      description: 'S3 bucket name for ground truth documents',
      exportName: 'AegisGroundTruthBucket',
    });

    new cdk.CfnOutput(this, 'KnowledgeBaseIdOutput', {
      value: this.knowledgeBaseId,
      description: 'Bedrock Knowledge Base ID',
      exportName: 'AegisKnowledgeBaseId',
    });

    new cdk.CfnOutput(this, 'CollectionEndpoint', {
      value: collection.attrCollectionEndpoint,
      description: 'OpenSearch Serverless collection endpoint',
      exportName: 'AegisCollectionEndpoint',
    });
  }
}
