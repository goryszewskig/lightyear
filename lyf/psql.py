#! /usr/bin/env python
# LYF data integration function library

import lyf, logging
import psycopg2
import codecs
import re
import csv

from datetime import date, timedelta, datetime	# Date time
from dateutil.parser import parse	# Date parser

# Class for youtube videos
class DB():
	# Initialiser
	def __init__(self):
		psql_db = lyf.get_config('POSTGRESQL', 'Database')
		psql_user = lyf.get_config('POSTGRESQL', 'Username')
		psql_schema = lyf.get_config('POSTGRESQL', 'Default_Schema')

		self.conn = psycopg2.connect('dbname=%s user=%s' % (psql_db, psql_user))
		self.cursor = self.conn.cursor()
		self.execute("SET search_path = '%s';" % psql_schema)

	# Execute SQL and optionally commit or rollback. Return 1 for success, 0 for error
	def execute(self, sql, values=[], commit=False, log=True):
		try:
			self.cursor.execute(sql, values)
			if commit:
				self.conn.commit()
			return(1)
		except Exception as err:
			self.conn.rollback()
			if log:
				logging.error('PSQL Error: %s' % err)
			return(0)

	# Truncate table
	def truncate(self, table):
		sql = 'TRUNCATE TABLE %s;' % qualify_schema(table)
		return(self.execute(sql))

	# Insert a single row to a table
	def insert(self, table, row):
		sql = 'INSERT INTO %s (' % qualify_schema(table)
		sql += ', '.join(row.keys())
		sql += ') VALUES ('
		sql += ', '.join(['%s' for key, val in row.items()]) # Placeholders
		sql += ')'

		values = [val for key, val in row.items()]
		status = self.execute(sql, values) # Attempt to insert the record
		return(status)

	# Insert or update a row to a table
	def upsert(self, table, row, keys):
		table = qualify_schema(table)
		update_where = [col + ' = %s' for col in keys]
		where_vals = []
		for key in keys:
			where_vals.append(row[key])

		insert_cols = [col for col, val in row.items()]
		insert_plch = [r'%s' for col, val in row.items()]
		insert_vals = [val for col, val in row.items()]
		all_vals = insert_vals + where_vals + insert_vals

		sql = 'WITH upsert AS (UPDATE %s SET (%s) = (%s) ' % (table, ', '.join(insert_cols), ', '.join(insert_plch))
		sql += 'WHERE %s ' % ' AND '.join(update_where)
		sql += 'RETURNING *) INSERT INTO %s (%s) SELECT %s ' % (table, ', '.join(insert_cols), ', '.join(insert_plch))
		sql += 'WHERE NOT EXISTS (SELECT * FROM upsert);'

		status = self.execute(sql, all_vals)
		return(status)

	# Update values on a table based on a filter
	def update(self, table, update_row, filter_row):
		table = qualify_schema(table)
		update_where = [key + ' = %s' for key in filter_row.keys()]
		update_cols = [col for col, val in update_row.items()]
		update_plch = [r'%s' for col, val in update_row.items()]

		update_vals = [val for col, val in update_row.items()]
		filter_vals = [val for col, val in filter_row.items()]
		all_vals = update_vals + filter_vals

		sql = 'UPDATE %s SET (%s) = (%s) ' % (table, ', '.join(update_cols), ', '.join(update_plch))
		sql += 'WHERE %s;' % ' AND '.join(update_where)

		status = self.execute(sql, all_vals)
		return(status)

	# Delete from table based on a filter
	def delete(self, table, filter_row):
		table = qualify_schema(table)
		delete_where = [key + ' = %s' for key in filter_row.keys()]
		filter_vals = [val for col, val in filter_row.items()]

		sql = 'DELETE FROM %s ' % table
		sql += 'WHERE %s;' % ' AND '.join(delete_where)

		status = self.execute(sql, filter_vals)
		return(status)

	# Update columns based on a lookup of another table
	def lookup(self, drv_table, lkp_table, drv_keys, lkp_keys, drv_update, lkp_update, only_nulls=True):
		# Qualify column names
		q_drv_keys = ['drv.%s' % val for val in drv_keys]
		q_lkp_keys = ['lkp.%s' % val for val in lkp_keys]
		q_lkp_update = ['lkp.%s' % val for val in lkp_update]

		where_clause = []
		for i in xrange(len(q_drv_keys)):
			where_clause.append('%s = %s' % (q_drv_keys[i], q_lkp_keys[i]))

		sql = 'UPDATE %s AS drv SET (%s) = (%s) ' % (qualify_schema(drv_table), ', '.join(drv_update), ', '.join(q_lkp_update))
		sql += 'FROM %s AS lkp WHERE %s' % (qualify_schema(lkp_table), ' AND '.join(where_clause))

		if only_nulls:
			null_only = ['drv.%s IS NULL' % val for val in drv_update]
			sql += ' AND %s' % ' AND '.join(null_only)

		sql += ';'
		status = self.execute(sql)
		return(status)

	# Resets a primary key serial back 1
	def reset_seq(self, table, primary_key):
		seq = '%s_%s_seq' % (qualify_schema(table), primary_key)
		self.execute('ALTER SEQUENCE %s RESTART WITH 1;' % seq)

	# Load CSV file into table, gets column names from CSV header
	def load_csv(self, table, csv_file):
		with open(csv_file, 'rb') as file:
			reader = csv.reader(file)
			i = 0
			for row in reader:
				if i == 0:
					columns = row
				else:
					rec = {}
					j = 0
					for val in row:
						if (val == ''):
							val = None
						rec[columns[j]] = val
						j += 1
					if (len(rec) > 0):
						self.insert(qualify_schema(table), rec)
				i += 1

	# Query and retrieve the records
	def query(self, sql, vals=[]):
		results = []
		self.execute(sql, vals)
		columns = [desc.name for desc in self.cursor.description]

		# Loop through results
		for result in self.cursor.fetchall():
			rec = {}
			for x in xrange(len(result)):
				rec[columns[x]] = result[x]
			results.append(rec)

		return(results)

	# Close the cursor and connection. Commit by default
	def close(self, commit=True):
		if commit:
			self.conn.commit()
		self.cursor.close()
		self.conn.close()

# Adds the default schema name to the table if not already present
def qualify_schema(table) :
	if re.search('\.', table) is None:
		table = '%s.%s' % (lyf.get_config('POSTGRESQL', 'Default_Schema'), table)
	return(table)

# Load Google Analytics dimension table
def load_ga_dim(full_mode, table, ga_dims, columns, keys):
	try:
		end_date = date.today().strftime('%Y-%m-%d') # Fetch up to today
		db = DB() # Connect to DB

		if full_mode:
			db.truncate(table) # Truncate table

			# Insert 0 row
			primary_key = re.search('d_ga_(.*?)$', table).group(1)
			primary_key += '_id'
			rec = {primary_key : -1}

			db.reset_seq(table, primary_key)

			db.insert(table, rec)
			db.conn.commit()

			start_date = lyf.get_config('ETL', 'Extract_Date')
		else:
			start_date = end_date

		# Connect to Google Analytics
		service = lyf.google_api('analytics', 'v3', ['https://www.googleapis.com/auth/analytics.readonly'])
		metrics = 'ga:sessions'
		dims = ','.join(ga_dims)
		results = lyf.ga_query(service, start_date, end_date, metrics, dims)

		inserts = 0
		for row in results:
			rec = {}
			i = 0
			for key in columns:
				rec[key] = row[i]
				i += 1
			inserts += db.upsert(table, rec, keys)

		db.close()

		if full_mode:
			mode = 'Full'
		else:
			mode = 'Incremental'
		logging.info('Merged %s/%s rows into %s (%s).' % (inserts, len(results), table, mode))
	except Exception as err:
		logging.error(err)
