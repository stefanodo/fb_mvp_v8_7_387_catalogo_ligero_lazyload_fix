CREATE TABLE IF NOT EXISTS centers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS warehouses (
                id SERIAL PRIMARY KEY,
                center_id INTEGER REFERENCES centers(id),
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                code VARCHAR(100) UNIQUE,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS productions (
                id SERIAL PRIMARY KEY,
                center_id INTEGER REFERENCES centers(id),
                warehouse_id INTEGER REFERENCES warehouses(id),
                status VARCHAR(50) DEFAULT 'DRAFT',
                note TEXT,
                production_group VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(150) UNIQUE,
                email VARCHAR(255),
                full_name VARCHAR(255),
                name VARCHAR(255),
                role VARCHAR(100) DEFAULT '',
                center_id INTEGER DEFAULT 0,
                password_hash VARCHAR(255),
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS suppliers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                vat_number VARCHAR(100),
                contact_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS recipes (
                id SERIAL PRIMARY KEY,
                code VARCHAR(100) UNIQUE,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(255),
                subcategory VARCHAR(255),
                is_subrecipe INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                yield_portions NUMERIC DEFAULT 0,
                yield_final_qty NUMERIC DEFAULT 0,
                yield_final_unit VARCHAR(50) DEFAULT '',
                waste_pct NUMERIC DEFAULT 0,
                contingency_pct NUMERIC DEFAULT 0,
                prep_steps TEXT,
                allergens TEXT,
                target_food_cost_pct NUMERIC DEFAULT 0,
                target_margin_pct NUMERIC DEFAULT 0,
                manual_price NUMERIC DEFAULT 0,
                suggested_price NUMERIC DEFAULT 0,
                cost_supplier_id INTEGER,
                scope_global TEXT,
                scope_centers TEXT,
                prep_time_min NUMERIC DEFAULT 0,
                cook_time_min NUMERIC DEFAULT 0,
                rest_time_min NUMERIC DEFAULT 0,
                labor_people NUMERIC DEFAULT 0,
                labor_hourly_cost NUMERIC DEFAULT 0,
                indirect_sales_base NUMERIC DEFAULT 0,
                indirect_rent_amount NUMERIC DEFAULT 0,
                indirect_rent_tax_mode INTEGER DEFAULT 0,
                indirect_services_amount NUMERIC DEFAULT 0,
                indirect_services_tax_mode INTEGER DEFAULT 0,
                indirect_admin_amount NUMERIC DEFAULT 0,
                indirect_admin_tax_mode INTEGER DEFAULT 0,
                indirect_marketing_amount NUMERIC DEFAULT 0,
                indirect_marketing_tax_mode INTEGER DEFAULT 0,
                indirect_other_amount NUMERIC DEFAULT 0,
                indirect_other_tax_mode INTEGER DEFAULT 0,
                salary_cost_amount NUMERIC DEFAULT 0,
                recipe_photo_path VARCHAR(512),
                instructions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS recipe_ingredients (
                id SERIAL PRIMARY KEY,
                recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
                item_id INTEGER,
                quantity NUMERIC,
                unit VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS inventory_sessions (
                id SERIAL PRIMARY KEY,
                center_id INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS inventory_counts (
                id SERIAL PRIMARY KEY,
                session_id INTEGER REFERENCES inventory_sessions(id) ON DELETE CASCADE,
                item_id INTEGER,
                counted_quantity NUMERIC,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS waste_records (
                id SERIAL PRIMARY KEY,
                center_id INTEGER,
                item_id INTEGER,
                qty NUMERIC,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS pos_integrations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                config JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS pos_sales_daily (
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL DEFAULT 0,
                sale_date TEXT NOT NULL,
                business_type TEXT NOT NULL DEFAULT 'restaurant',
                channel TEXT NOT NULL DEFAULT '',
                tickets INTEGER NOT NULL DEFAULT 0,
                covers INTEGER NOT NULL DEFAULT 0,
                net_sales DOUBLE PRECISION NOT NULL DEFAULT 0,
                gross_sales DOUBLE PRECISION NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS pos_sales_item_daily (
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL DEFAULT 0,
                sale_date TEXT NOT NULL,
                recipe_id INTEGER NOT NULL DEFAULT 0,
                recipe_name TEXT NOT NULL DEFAULT '',
                pos_item_code TEXT NOT NULL DEFAULT '',
                pos_item_name TEXT NOT NULL DEFAULT '',
                qty_sold DOUBLE PRECISION NOT NULL DEFAULT 0,
                net_sales DOUBLE PRECISION NOT NULL DEFAULT 0,
                gross_sales DOUBLE PRECISION NOT NULL DEFAULT 0,
                channel TEXT NOT NULL DEFAULT '',
                business_type TEXT NOT NULL DEFAULT 'restaurant',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS recipe_import_drafts (
                id SERIAL PRIMARY KEY,
                recipe_name TEXT NOT NULL,
                recipe_type TEXT DEFAULT 'RECETA',
                category TEXT DEFAULT 'OTRO',
                subcategory TEXT,
                service_family TEXT DEFAULT 'OTRO',
                yield_quantity NUMERIC,
                yield_unit TEXT DEFAULT 'kg',
                portions INTEGER,
                elaboration_steps_json JSONB,
                allergens_json JSONB,
                labor_json JSONB,
                import_status TEXT DEFAULT 'BORRADOR_IA',
                cost_status TEXT DEFAULT 'NO_CALCULADO',
                confidence NUMERIC DEFAULT 0,
                warnings_json JSONB,
                source_type TEXT,
                raw_input_text TEXT,
                raw_ia_json JSONB,
                ia_provider TEXT,
                ia_model TEXT,
                process_time_s NUMERIC,
                created_by TEXT,
                validated_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                validated_at TIMESTAMP,
                review_at TIMESTAMP,
                converted_recipe_id INTEGER
            );

CREATE TABLE IF NOT EXISTS recipe_import_ingredients (
                id SERIAL PRIMARY KEY,
                draft_id INTEGER REFERENCES recipe_import_drafts(id) ON DELETE CASCADE,
                original_text TEXT,
                normalized_name TEXT NOT NULL,
                ingredient_type TEXT DEFAULT 'ARTICULO',
                quantity_net NUMERIC,
                unit TEXT,
                waste_percent NUMERIC DEFAULT 0,
                quantity_gross NUMERIC,
                match_status TEXT DEFAULT 'PENDIENTE_ALTA',
                matched_item_id INTEGER,
                matched_item_name TEXT,
                matched_subrecipe_id INTEGER,
                matched_subrecipe_name TEXT,
                candidates_json JSONB,
                needs_admin_validation INTEGER DEFAULT 1,
                notes TEXT,
                original_quantity NUMERIC,
                original_unit TEXT,
                conversion_status TEXT DEFAULT 'NO_REQUIERE_CONVERSION',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS recipe_import_audit_log (
                id SERIAL PRIMARY KEY,
                draft_id INTEGER,
                ingredient_id INTEGER,
                action TEXT NOT NULL,
                actor TEXT,
                previous_value_json JSONB,
                new_value_json JSONB,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS recipe_modifiers(
                id SERIAL PRIMARY KEY,
                recipe_id INTEGER NOT NULL DEFAULT 0,
                code TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                modifier_type TEXT NOT NULL DEFAULT 'REVIEW',
                action TEXT NOT NULL DEFAULT 'REVIEW',
                item_id INTEGER NOT NULL DEFAULT 0,
                subrecipe_id INTEGER NOT NULL DEFAULT 0,
                qty_delta_base DOUBLE PRECISION NOT NULL DEFAULT 0,
                unit_base TEXT NOT NULL DEFAULT 'g',
                price_extra DOUBLE PRECISION NOT NULL DEFAULT 0,
                affects_stock INTEGER NOT NULL DEFAULT 1,
                confidence TEXT NOT NULL DEFAULT 'MANUAL',
                notes TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS pos_modifier_map(
                id SERIAL PRIMARY KEY,
                provider_name TEXT NOT NULL DEFAULT '',
                business_type TEXT NOT NULL DEFAULT '',
                pos_modifier_name TEXT NOT NULL DEFAULT '',
                normalized_code TEXT NOT NULL DEFAULT '',
                recipe_id INTEGER NOT NULL DEFAULT 0,
                modifier_id INTEGER NOT NULL DEFAULT 0,
                action_status TEXT NOT NULL DEFAULT 'ACTIVE',
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS pos_sales_modifier_daily(
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL DEFAULT 0,
                sale_date TEXT,
                recipe_id INTEGER NOT NULL DEFAULT 0,
                recipe_name TEXT NOT NULL DEFAULT '',
                pos_item_code TEXT NOT NULL DEFAULT '',
                pos_item_name TEXT NOT NULL DEFAULT '',
                pos_modifier_name TEXT NOT NULL DEFAULT '',
                normalized_modifier_code TEXT NOT NULL DEFAULT '',
                modifier_id INTEGER NOT NULL DEFAULT 0,
                qty_sold DOUBLE PRECISION NOT NULL DEFAULT 0,
                channel TEXT NOT NULL DEFAULT '',
                business_type TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'REQUIERE_MAPEO',
                confidence TEXT NOT NULL DEFAULT 'LOW',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS pos_modifier_consumption_audit(
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL DEFAULT 0,
                sale_date TEXT,
                recipe_id INTEGER NOT NULL DEFAULT 0,
                modifier_id INTEGER NOT NULL DEFAULT 0,
                item_id INTEGER NOT NULL DEFAULT 0,
                subrecipe_id INTEGER NOT NULL DEFAULT 0,
                qty_delta_base DOUBLE PRECISION NOT NULL DEFAULT 0,
                unit_base TEXT NOT NULL DEFAULT 'g',
                status TEXT NOT NULL DEFAULT 'PREVIEW',
                reason TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS pos_modifier_review_queue(
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL DEFAULT 0,
                sale_date TEXT DEFAULT (CURRENT_DATE::text),
                recipe_id INTEGER NOT NULL DEFAULT 0,
                recipe_name TEXT NOT NULL DEFAULT '',
                pos_item_name TEXT NOT NULL DEFAULT '',
                raw_customer_note TEXT NOT NULL DEFAULT '',
                normalized_note TEXT NOT NULL DEFAULT '',
                suggested_status TEXT NOT NULL DEFAULT 'REQUIERE_MAPEO',
                suggested_action TEXT NOT NULL DEFAULT '',
                suggested_delta_json TEXT NOT NULL DEFAULT '',
                confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                review_status TEXT NOT NULL DEFAULT 'PENDIENTE',
                learned_modifier_id INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_sources(
                id SERIAL PRIMARY KEY,
                name TEXT,
                type TEXT,
                provider_name TEXT,
                api_mode TEXT,
                active INTEGER DEFAULT 1,
                config_json JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_sales_raw(
                id SERIAL PRIMARY KEY,
                tpv_source_id INTEGER,
                raw_payload_json JSONB,
                received_at TIMESTAMP,
                import_status TEXT,
                error_message TEXT,
                hash_deduplication TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_sales(
                id SERIAL PRIMARY KEY,
                tpv_source_id INTEGER,
                external_sale_id TEXT,
                external_ticket_id TEXT,
                restaurant_id INTEGER,
                sale_datetime TEXT,
                business_date TEXT,
                shift TEXT,
                channel TEXT,
                table_number TEXT,
                waiter_name TEXT,
                total_amount DOUBLE PRECISION DEFAULT 0,
                payment_method TEXT,
                sale_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_sale_lines(
                id SERIAL PRIMARY KEY,
                tpv_sale_id INTEGER,
                external_line_id TEXT,
                product_name_raw TEXT,
                product_code_raw TEXT,
                matched_recipe_id INTEGER,
                matched_item_id INTEGER,
                quantity DOUBLE PRECISION DEFAULT 0,
                unit_price DOUBLE PRECISION DEFAULT 0,
                discount_amount DOUBLE PRECISION DEFAULT 0,
                tax_rate DOUBLE PRECISION DEFAULT 0,
                total_line_amount DOUBLE PRECISION DEFAULT 0,
                line_status TEXT,
                mapping_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_product_mappings(
                id SERIAL PRIMARY KEY,
                tpv_source_id INTEGER,
                product_name_raw TEXT,
                product_code_raw TEXT,
                matched_recipe_id INTEGER,
                matched_item_id INTEGER,
                confidence DOUBLE PRECISION DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_modifiers(
                id SERIAL PRIMARY KEY,
                tpv_sale_line_id INTEGER,
                modifier_text_raw TEXT,
                modifier_name TEXT,
                modifier_type TEXT,
                interpreted_action TEXT,
                affects_stock TEXT,
                linked_item_id INTEGER,
                linked_recipe_id INTEGER,
                qty_delta DOUBLE PRECISION,
                unit TEXT,
                confidence DOUBLE PRECISION DEFAULT 0,
                review_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_modifier_rules(
                id SERIAL PRIMARY KEY,
                rule_text TEXT,
                normalized_text TEXT,
                modifier_type TEXT,
                linked_item_id INTEGER,
                linked_recipe_id INTEGER,
                qty_delta DOUBLE PRECISION,
                unit TEXT,
                affects_stock TEXT,
                confidence_default DOUBLE PRECISION DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS tpv_consumption_events(
                id SERIAL PRIMARY KEY,
                tpv_sale_id INTEGER,
                tpv_sale_line_id INTEGER,
                recipe_id INTEGER,
                item_id INTEGER,
                production_id INTEGER,
                qty_theoretical DOUBLE PRECISION DEFAULT 0,
                unit TEXT,
                cost_amount DOUBLE PRECISION DEFAULT 0,
                source TEXT,
                confidence DOUBLE PRECISION DEFAULT 0,
                review_status TEXT,
                movement_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS bar_businesses(
                business_id TEXT PRIMARY KEY,
                business_name TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                data_scope TEXT DEFAULT 'demo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS bar_locations(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                restaurant_name TEXT,
                bar_id TEXT,
                bar_name TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(business_id,restaurant_id,bar_id)
            );

CREATE TABLE IF NOT EXISTS bar_items(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                bar_id TEXT,
                code TEXT,
                name TEXT,
                normalized_name TEXT,
                item_type TEXT,
                family TEXT,
                base_unit TEXT,
                purchase_unit TEXT,
                purchase_qty DOUBLE PRECISION DEFAULT 0,
                purchase_price_2025 DOUBLE PRECISION DEFAULT 0,
                purchase_price_2026 DOUBLE PRECISION DEFAULT 0,
                cost_per_base_unit_2026 DOUBLE PRECISION DEFAULT 0,
                standard_waste_percent DOUBLE PRECISION DEFAULT 0,
                juice_yield_percent DOUBLE PRECISION DEFAULT NULL,
                juice_cost_per_ml_2026 DOUBLE PRECISION DEFAULT NULL,
                supplier_name_demo TEXT,
                min_stock DOUBLE PRECISION DEFAULT 0,
                max_stock DOUBLE PRECISION DEFAULT 0,
                location TEXT,
                active INTEGER DEFAULT 1,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                data_scope TEXT DEFAULT 'demo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(business_id,restaurant_id,bar_id,normalized_name)
            );

CREATE TABLE IF NOT EXISTS bar_stock_movements(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                bar_id TEXT,
                bar_item_id INTEGER,
                movement_type TEXT,
                qty DOUBLE PRECISION DEFAULT 0,
                unit TEXT,
                document_code TEXT,
                source_module TEXT,
                responsible_name TEXT,
                movement_datetime TIMESTAMP,
                notes TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS bar_productions(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                bar_id TEXT,
                code TEXT,
                name TEXT,
                production_type TEXT,
                yield_qty DOUBLE PRECISION DEFAULT 0,
                yield_unit TEXT,
                cost_total_2026 DOUBLE PRECISION DEFAULT 0,
                cost_per_unit_2026 DOUBLE PRECISION DEFAULT 0,
                standard_waste_percent DOUBLE PRECISION DEFAULT 0,
                shelf_life_days INTEGER DEFAULT 0,
                lot TEXT,
                responsible TEXT,
                storage_location TEXT,
                procedure_text TEXT,
                status TEXT,
                stock_actual DOUBLE PRECISION DEFAULT 0,
                used_in_recipes TEXT,
                es_vendible INTEGER DEFAULT 0,
                sale_price DOUBLE PRECISION DEFAULT NULL,
                notes TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                data_scope TEXT DEFAULT 'demo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(business_id,restaurant_id,bar_id,code)
            );

CREATE TABLE IF NOT EXISTS bar_production_lines(
                id SERIAL PRIMARY KEY,
                bar_production_id INTEGER,
                bar_item_id INTEGER,
                item_name TEXT,
                qty_net DOUBLE PRECISION DEFAULT 0,
                unit TEXT,
                waste_percent DOUBLE PRECISION DEFAULT 0,
                qty_gross DOUBLE PRECISION DEFAULT 0,
                cost_unit_2026 DOUBLE PRECISION DEFAULT 0,
                cost_total_net_2026 DOUBLE PRECISION DEFAULT 0,
                cost_total_gross_2026 DOUBLE PRECISION DEFAULT 0,
                notes TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0
            );

CREATE TABLE IF NOT EXISTS bar_production_stock_movements(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                bar_id TEXT,
                bar_production_id INTEGER,
                movement_type TEXT,
                qty DOUBLE PRECISION DEFAULT 0,
                unit TEXT,
                source_module TEXT,
                responsible_name TEXT,
                movement_datetime TIMESTAMP,
                notes TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS cocktail_recipes(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                bar_id TEXT,
                code TEXT,
                name TEXT,
                category TEXT,
                cocktail_type TEXT,
                glass_type TEXT,
                serving_size_ml DOUBLE PRECISION DEFAULT 0,
                yield_qty DOUBLE PRECISION DEFAULT 1,
                yield_unit TEXT,
                alcohol_percentage_estimated DOUBLE PRECISION DEFAULT 0,
                difficulty TEXT,
                preparation_time_minutes DOUBLE PRECISION DEFAULT 0,
                seasonality TEXT,
                sale_price DOUBLE PRECISION DEFAULT 0,
                suggested_price DOUBLE PRECISION DEFAULT 0,
                target_margin_percent DOUBLE PRECISION DEFAULT 0,
                contingency_percent DOUBLE PRECISION DEFAULT 0,
                cost_2025_orientative DOUBLE PRECISION DEFAULT 0,
                cost_2026_net DOUBLE PRECISION DEFAULT 0,
                cost_2026_gross_with_waste DOUBLE PRECISION DEFAULT 0,
                margin_percent_2026 DOUBLE PRECISION DEFAULT 0,
                cost_per_ml DOUBLE PRECISION DEFAULT 0,
                contains_alcohol INTEGER DEFAULT 1,
                allergens_json JSONB,
                warnings_json JSONB,
                photo_path TEXT,
                notes TEXT,
                status TEXT,
                active INTEGER DEFAULT 1,
                created_by TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                data_scope TEXT DEFAULT 'demo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(business_id,restaurant_id,bar_id,code)
            );

CREATE TABLE IF NOT EXISTS cocktail_recipe_lines(
                id SERIAL PRIMARY KEY,
                cocktail_recipe_id INTEGER,
                origin TEXT,
                bar_item_id INTEGER,
                bar_production_id INTEGER,
                ingredient_name TEXT,
                qty_net DOUBLE PRECISION DEFAULT 0,
                unit TEXT,
                waste_percent DOUBLE PRECISION DEFAULT 0,
                qty_gross DOUBLE PRECISION DEFAULT 0,
                cost_unit_2026 DOUBLE PRECISION DEFAULT 0,
                cost_total_net_2026 DOUBLE PRECISION DEFAULT 0,
                cost_total_gross_2026 DOUBLE PRECISION DEFAULT 0,
                supplier_name_demo TEXT,
                stock_available DOUBLE PRECISION DEFAULT 0,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0
            );

CREATE TABLE IF NOT EXISTS cocktail_recipe_steps(
                id SERIAL PRIMARY KEY,
                cocktail_recipe_id INTEGER,
                step_number INTEGER,
                instruction TEXT,
                demo_data INTEGER DEFAULT 0
            );

CREATE TABLE IF NOT EXISTS cocktail_cost_history(
                id SERIAL PRIMARY KEY,
                cocktail_recipe_id INTEGER,
                cost_per_serving_net_2026 DOUBLE PRECISION DEFAULT 0,
                cost_per_serving_gross_2026 DOUBLE PRECISION DEFAULT 0,
                sale_price DOUBLE PRECISION DEFAULT 0,
                margin_percent DOUBLE PRECISION DEFAULT 0,
                calculated_at TIMESTAMP,
                source TEXT,
                notes TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0
            );

CREATE TABLE IF NOT EXISTS bar_alerts(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                bar_id TEXT,
                alert_code TEXT,
                alert_text TEXT,
                severity TEXT,
                blocking INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(business_id,restaurant_id,bar_id,alert_code)
            );

CREATE TABLE IF NOT EXISTS bar_tpv_mappings(
                id SERIAL PRIMARY KEY,
                business_id TEXT,
                restaurant_id TEXT,
                bar_id TEXT,
                cocktail_recipe_id INTEGER,
                product_name_raw TEXT,
                product_code_raw TEXT,
                mapping_status TEXT,
                connection_status TEXT,
                demo_data INTEGER DEFAULT 0,
                non_productive_demo INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(business_id,restaurant_id,bar_id,product_code_raw)
            );

CREATE TABLE IF NOT EXISTS supplier_item_prices(
                id SERIAL PRIMARY KEY,
                supplier_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                center_id INTEGER,
                price_per_purchase DOUBLE PRECISION NOT NULL,
                purchase_unit TEXT NOT NULL,
                purchase_to_base_factor DOUBLE PRECISION NOT NULL,
                is_preferred BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP NOT NULL,
                FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            );

CREATE TABLE IF NOT EXISTS movements(
                id SERIAL PRIMARY KEY,
                movement_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                center_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                qty DOUBLE PRECISION NOT NULL,
                unit TEXT NOT NULL,
                note TEXT,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY(item_id) REFERENCES items(id)
            );

CREATE TABLE IF NOT EXISTS item_location_prefs(
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                min_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
                max_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
                UNIQUE(center_id, warehouse_id, item_id)
            );

CREATE TABLE IF NOT EXISTS production_lines(
                id SERIAL PRIMARY KEY,
                production_id INTEGER NOT NULL,
                line_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                qty_base DOUBLE PRECISION NOT NULL,
                input_unit TEXT NOT NULL,
                qty_input DOUBLE PRECISION NOT NULL,
                FOREIGN KEY(production_id) REFERENCES productions(id)
            );

CREATE TABLE IF NOT EXISTS orders(
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TIMESTAMP NOT NULL,
                note TEXT
            );

CREATE TABLE IF NOT EXISTS order_free_notes(
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL DEFAULT 0,
                center_id INTEGER NOT NULL DEFAULT 0,
                text TEXT NOT NULL DEFAULT '',
                target_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'IDEA',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS order_lines(
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                qty_base DOUBLE PRECISION NOT NULL,
                input_unit TEXT NOT NULL,
                qty_input DOUBLE PRECISION NOT NULL,
                supplier_id INTEGER,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );

CREATE TABLE IF NOT EXISTS receipts(
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL,
                warehouse_id INTEGER NOT NULL,
                supplier_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                doc_number TEXT,
                doc_date TEXT,
                note TEXT,
                created_at TIMESTAMP NOT NULL,
                validated_at TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS receipt_lines(
                id SERIAL PRIMARY KEY,
                receipt_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                qty_input DOUBLE PRECISION NOT NULL,
                input_unit TEXT NOT NULL,
                factor DOUBLE PRECISION NOT NULL,
                qty_base DOUBLE PRECISION NOT NULL,
                price_unit DOUBLE PRECISION,
                line_total DOUBLE PRECISION,
                FOREIGN KEY(receipt_id) REFERENCES receipts(id)
            );

CREATE TABLE IF NOT EXISTS receipt_photos(
                id SERIAL PRIMARY KEY,
                receipt_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY(receipt_id) REFERENCES receipts(id)
            );

CREATE TABLE IF NOT EXISTS receipt_ocr_runs(
                id SERIAL PRIMARY KEY,
                receipt_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                supplier_raw TEXT,
                doc_number_raw TEXT,
                doc_date_raw TEXT,
                supplier_phone_raw TEXT,
                supplier_email_raw TEXT,
                supplier_tax_id_raw TEXT,
                supplier_address_raw TEXT,
                summary TEXT,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY(receipt_id) REFERENCES receipts(id)
            );

CREATE TABLE IF NOT EXISTS receipt_ocr_lines(
                id SERIAL PRIMARY KEY,
                ocr_run_id INTEGER NOT NULL,
                source_text TEXT,
                item_name_raw TEXT,
                qty_raw TEXT,
                unit_raw TEXT,
                price_raw TEXT,
                amount_raw TEXT,
                discount_raw TEXT,
                vat_raw TEXT,
                qty_basis_raw TEXT,
                qty_aux_raw TEXT,
                matched_item_id INTEGER,
                matched_item_name TEXT,
                review_status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY(ocr_run_id) REFERENCES receipt_ocr_runs(id)
            );

CREATE TABLE IF NOT EXISTS supplier_documents(
                id SERIAL PRIMARY KEY,
                supplier_id INTEGER NOT NULL DEFAULT 0,
                center_id INTEGER NOT NULL DEFAULT 0,
                doc_type TEXT NOT NULL DEFAULT 'albaran',
                doc_number TEXT NOT NULL DEFAULT '',
                doc_date TEXT,
                period_month TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                stored_path TEXT NOT NULL DEFAULT '',
                file_sha256 TEXT NOT NULL DEFAULT '',
                ocr_status TEXT NOT NULL DEFAULT 'PENDING',
                reconciliation_status TEXT NOT NULL DEFAULT 'PENDING',
                accounting_status TEXT NOT NULL DEFAULT 'PENDING',
                payment_status TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
                base_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                vat_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                total_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'EUR',
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS supplier_document_reconciliations(
                id SERIAL PRIMARY KEY,
                receipt_document_id INTEGER NOT NULL DEFAULT 0,
                invoice_document_id INTEGER NOT NULL DEFAULT 0,
                supplier_id INTEGER NOT NULL DEFAULT 0,
                center_id INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'PENDING',
                base_diff DOUBLE PRECISION NOT NULL DEFAULT 0,
                vat_diff DOUBLE PRECISION NOT NULL DEFAULT 0,
                total_diff DOUBLE PRECISION NOT NULL DEFAULT 0,
                warnings_json JSONB NOT NULL DEFAULT '[]',
                approved_by TEXT NOT NULL DEFAULT '',
                approved_at TIMESTAMP NOT NULL DEFAULT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS supplier_payment_proposals(
                id SERIAL PRIMARY KEY,
                supplier_id INTEGER NOT NULL DEFAULT 0,
                center_id INTEGER NOT NULL DEFAULT 0,
                invoice_document_id INTEGER NOT NULL DEFAULT 0,
                reconciliation_id INTEGER NOT NULL DEFAULT 0,
                due_date TEXT NOT NULL DEFAULT '',
                amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'EUR',
                payment_method TEXT NOT NULL DEFAULT '',
                supplier_iban_masked TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PROPOSED',
                human_approval_required BOOLEAN NOT NULL DEFAULT TRUE,
                approved_by TEXT NOT NULL DEFAULT '',
                approved_at TIMESTAMP NOT NULL DEFAULT NULL,
                bank_execution_ref TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE IF NOT EXISTS accounting_export_batches(
                id SERIAL PRIMARY KEY,
                center_id INTEGER NOT NULL DEFAULT 0,
                period_from TEXT NOT NULL DEFAULT '',
                period_to TEXT NOT NULL DEFAULT '',
                supplier_id INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                file_path TEXT NOT NULL DEFAULT '',
                summary_json JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT NOT NULL DEFAULT ''
            );

ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255);

ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(100) DEFAULT '';

ALTER TABLE users ADD COLUMN IF NOT EXISTS center_id INTEGER DEFAULT 0;

DO $$
BEGIN
    BEGIN
        EXECUTE 'ALTER TABLE users ALTER COLUMN is_active TYPE INTEGER USING (CASE WHEN is_active THEN 1 ELSE 0 END)';
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Skipping alter users.is_active: %', SQLERRM;
    END;
END;
$$;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS is_producible INTEGER NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS produced_item_id INTEGER NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS yield_portions NUMERIC NOT NULL DEFAULT 1;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS yield_final_qty NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS yield_final_unit VARCHAR(50) NOT NULL DEFAULT 'g';

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS is_active INTEGER NOT NULL DEFAULT 1;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS recipe_photo_path VARCHAR(512);

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS prep_time_min NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS cook_time_min NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS rest_time_min NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS labor_people NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS labor_hourly_cost NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS indirect_sales_base NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS salary_cost_amount NUMERIC NOT NULL DEFAULT 0;

ALTER TABLE pos_sales_daily ALTER COLUMN sale_date TYPE TEXT USING sale_date::text;

ALTER TABLE pos_sales_item_daily ALTER COLUMN sale_date TYPE TEXT USING sale_date::text;

ALTER TABLE pos_sales_modifier_daily ALTER COLUMN sale_date TYPE TEXT USING sale_date::text;

ALTER TABLE pos_modifier_consumption_audit ALTER COLUMN sale_date TYPE TEXT USING sale_date::text;

ALTER TABLE pos_modifier_review_queue ALTER COLUMN sale_date TYPE TEXT USING sale_date::text;

ALTER TABLE tpv_sales ALTER COLUMN sale_datetime TYPE TEXT USING sale_datetime::text;

ALTER TABLE tpv_sales ALTER COLUMN business_date TYPE TEXT USING business_date::text;

ALTER TABLE bar_stock_movements ALTER COLUMN movement_datetime TYPE TEXT USING movement_datetime::text;

ALTER TABLE bar_stock_movements ALTER COLUMN created_at TYPE TEXT USING created_at::text;

ALTER TABLE receipts ADD COLUMN IF NOT EXISTS validated_at TEXT;

ALTER TABLE receipts ALTER COLUMN validated_at TYPE TEXT USING validated_at::text;

ALTER TABLE receipts ALTER COLUMN created_at TYPE TEXT USING created_at::text;

ALTER TABLE waste_records ADD COLUMN IF NOT EXISTS confirmed_at TEXT;

ALTER TABLE waste_records ALTER COLUMN confirmed_at TYPE TEXT USING confirmed_at::text;

ALTER TABLE waste_records ALTER COLUMN created_at TYPE TEXT USING created_at::text;

ALTER TABLE items ADD COLUMN IF NOT EXISTS unit TEXT NOT NULL DEFAULT '';

ALTER TABLE items ADD COLUMN IF NOT EXISTS min_qty DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE items ADD COLUMN IF NOT EXISTS max_qty DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE items ADD COLUMN IF NOT EXISTS current_price DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE items ADD COLUMN IF NOT EXISTS waste_default_pct DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE items ADD COLUMN IF NOT EXISTS stock_area TEXT NOT NULL DEFAULT '';

ALTER TABLE inventory_sessions ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;

ALTER TABLE inventory_sessions ADD COLUMN IF NOT EXISTS session_type TEXT NOT NULL DEFAULT 'MIXTO';

ALTER TABLE inventory_sessions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'DRAFT';

ALTER TABLE inventory_sessions ADD COLUMN IF NOT EXISTS note TEXT;

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'raw';

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS item_name TEXT;

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS family_key TEXT NOT NULL DEFAULT '';

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS warehouse_id INTEGER NOT NULL DEFAULT 0;

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS theoretical_qty DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS physical_qty DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS count_unit TEXT NOT NULL DEFAULT 'ud';

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS is_checked BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE inventory_counts ADD COLUMN IF NOT EXISTS unit_cost_snapshot DOUBLE PRECISION NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_supplier_documents_supplier ON supplier_documents(supplier_id,created_at);

CREATE INDEX IF NOT EXISTS idx_recipe_import_drafts_status ON recipe_import_drafts(import_status);

CREATE INDEX IF NOT EXISTS idx_recipe_import_ingredients_draft ON recipe_import_ingredients(draft_id);

CREATE INDEX IF NOT EXISTS idx_recipe_import_ingredients_status ON recipe_import_ingredients(match_status);

CREATE INDEX IF NOT EXISTS idx_recipe_modifiers_recipe ON recipe_modifiers(recipe_id,is_active);

CREATE INDEX IF NOT EXISTS idx_pos_modifier_map_norm ON pos_modifier_map(normalized_code,recipe_id,action_status);

CREATE INDEX IF NOT EXISTS idx_pos_sales_modifier_period ON pos_sales_modifier_daily(sale_date,center_id,recipe_id);

CREATE INDEX IF NOT EXISTS idx_pos_modifier_review_status ON pos_modifier_review_queue(review_status,recipe_id,created_at);