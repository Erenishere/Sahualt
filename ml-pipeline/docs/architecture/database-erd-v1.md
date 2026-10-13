# Database ERD V1

This Mermaid ERD reflects `20260910_001_catalog_core_v1`. It intentionally excludes deferred
RefreshSession, Search, Commerce, Analytics, FTS, and vector infrastructure.

```mermaid
erDiagram
    IAM_USERS {
        uuid id PK
        text email
        text email_normalized UK
        text password_hash
        text display_name
        text status
        timestamptz email_verified_at
        timestamptz last_login_at
        timestamptz created_at
        timestamptz updated_at
        timestamptz archived_at
    }

    CATALOG_VENDORS {
        uuid id PK
        text display_name
        text legal_name
        text slug UK
        text status
        uuid created_by_user_id FK
        timestamptz created_at
        timestamptz updated_at
        timestamptz archived_at
    }

    IAM_VENDOR_MEMBERSHIPS {
        uuid id PK
        uuid vendor_id FK
        uuid user_id FK
        text role
        text status
        timestamptz created_at
        timestamptz updated_at
    }

    CATALOG_CATEGORIES {
        uuid id PK
        uuid parent_id FK
        text name
        text slug UK
        text status
        integer sort_order
        timestamptz created_at
        timestamptz updated_at
        timestamptz archived_at
    }

    CATALOG_PRODUCTS {
        uuid id PK
        uuid vendor_id FK
        uuid category_id FK
        text name
        text description
        text brand_name
        text status
        timestamptz published_at
        uuid created_by_user_id FK
        uuid updated_by_user_id FK
        timestamptz created_at
        timestamptz updated_at
        timestamptz archived_at
    }

    CATALOG_PRODUCT_VARIANTS {
        uuid id PK
        uuid product_id FK
        text variant_code
        text sku
        text color
        text size
        text status
        boolean is_default
        timestamptz created_at
        timestamptz updated_at
        timestamptz archived_at
    }

    CATALOG_LISTINGS {
        uuid id PK
        uuid variant_id FK
        numeric price
        varchar currency
        text availability
        text status
        timestamptz created_at
        timestamptz updated_at
        timestamptz archived_at
    }

    INVENTORY_INVENTORY_BALANCES {
        uuid listing_id PK,FK
        integer on_hand_quantity
        integer reserved_quantity
        timestamptz updated_at
    }

    CATALOG_PRODUCT_IMAGES {
        uuid id PK
        uuid product_id FK
        uuid variant_id FK
        text storage_key UK
        text source_url
        text mime_type
        integer width
        integer height
        varchar sha256
        integer sort_order
        boolean is_primary
        text status
        timestamptz created_at
        timestamptz updated_at
        timestamptz archived_at
    }

    CATALOG_PRODUCT_EXTERNAL_REFS {
        uuid id PK
        uuid product_id FK
        text source_system UK
        text external_product_id UK
        varchar source_checksum
        timestamptz created_at
    }

    CATALOG_IMAGE_EXTERNAL_REFS {
        uuid id PK
        uuid image_id FK
        text source_system UK
        text external_image_id UK
        text source_path
        timestamptz created_at
    }

    INTEGRATION_OUTBOX_EVENTS {
        uuid id PK
        text event_type
        text aggregate_type
        uuid aggregate_id
        jsonb payload
        text status
        integer attempt_count
        timestamptz occurred_at
        timestamptz processed_at
        text last_error
    }

    AUDIT_AUDIT_LOG {
        uuid id PK
        uuid actor_user_id FK
        uuid vendor_id FK
        text entity_type
        uuid entity_id
        text action
        jsonb before_data
        jsonb after_data
        uuid request_id
        timestamptz created_at
    }

    INTEGRATION_SCHEMA_MIGRATIONS {
        text migration_id PK
        varchar checksum
        timestamptz applied_at
        text postgres_version
    }

    IAM_USERS o|--o{ CATALOG_VENDORS : creates
    IAM_USERS ||--o{ IAM_VENDOR_MEMBERSHIPS : has
    CATALOG_VENDORS ||--o{ IAM_VENDOR_MEMBERSHIPS : contains
    CATALOG_CATEGORIES o|--o{ CATALOG_CATEGORIES : parent_of
    CATALOG_VENDORS ||--o{ CATALOG_PRODUCTS : owns
    CATALOG_CATEGORIES o|--o{ CATALOG_PRODUCTS : classifies
    IAM_USERS o|--o{ CATALOG_PRODUCTS : authors
    CATALOG_PRODUCTS ||--o{ CATALOG_PRODUCT_VARIANTS : has
    CATALOG_PRODUCT_VARIANTS ||--o{ CATALOG_LISTINGS : offered_as
    CATALOG_LISTINGS ||--o| INVENTORY_INVENTORY_BALANCES : balances
    CATALOG_PRODUCTS ||--o{ CATALOG_PRODUCT_IMAGES : has
    CATALOG_PRODUCT_VARIANTS o|--o{ CATALOG_PRODUCT_IMAGES : scopes
    CATALOG_PRODUCTS ||--o{ CATALOG_PRODUCT_EXTERNAL_REFS : maps
    CATALOG_PRODUCT_IMAGES ||--o{ CATALOG_IMAGE_EXTERNAL_REFS : maps
    IAM_USERS o|--o{ AUDIT_AUDIT_LOG : acts
    CATALOG_VENDORS o|--o{ AUDIT_AUDIT_LOG : scopes
```

Notes:

- The image-to-variant relationship is implemented as composite FK `(variant_id, product_id)` to
  ensure Product consistency.
- External-reference uniqueness is composite by `(source_system, external_*_id)`; Mermaid's `UK`
  marker is descriptive at the field level.
- Outbox aggregate and Audit entity IDs are polymorphic UUID references, not foreign keys.
- `integration.schema_migrations` is migration infrastructure and has no domain relationship.
