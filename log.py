import re
from os import path
from sys import argv

reg_types = {'int': '%d', 'long long': '%lld', 'long': '%ld', 'float': '%f', 'char': '%c', 
			'_Bool': '%d', 'BOOL': '%d', 'unsigned long long': '%llu', 'double': '%f',
			'unsigned int': '%d', 'unsigned char': '%c', 'id': '%@', 'unsigned': '%d', 'unsigned short': '%hu',}

bad_types = {'void', 'Class', 'SEL'}
base_prefixes = {'NS', 'CF', 'UI', 'CA'}

extra_types = set()

sep = False
file = False
no_newline = False
help = False
idclass = False

file_location = '/var/mobile/Documents/nslog.log'
parse_location = ''
prefix = 'NSLG'

def getLogString(funcname, interface):
	funcname = funcname.replace('CDUnknownBlockType', 'id').replace('out id *', 'id').replace('id *', 'id').replace(';', '').rstrip()
	funcname = re.sub(r'(\<.*\>|\/\*.*\*\/)', '', funcname.replace('oneway', '').replace('out ', 'id').replace('-(', '- (').replace('+(', '+ ('))
	if 'cxx_destruct' in funcname:
		return ''

	orig_string = ''
	ret_type = funcname.split('(')[1].split(')')[0]

	if ret_type != 'void':
		orig_string = f'\t{ret_type} orig = %orig;'

	fixed_type = ret_type.replace('*', '').strip()
	if fixed_type not in reg_types and fixed_type not in bad_types and ret_type[:2] not in base_prefixes:
		extra_types.add(fixed_type)

	log_string = f'\tNSString *log = [NSString stringWithFormat:@"{prefix}: Called'
	vars_string = ''
	ret_string = '\treturn ' + ('%' if ret_type == 'void' else '') + 'orig;'

	first_index = funcname.find(')') + 1
	past_index = funcname.find(')') + 1
	sec = ''

	for n, i in enumerate(funcname[past_index:]):
		sec += i
		if (i == ' ' and ')' in sec) or n == len(funcname[first_index:]) - 1:
			sec = sec.strip()
			past_index = n + 1
			val_name = sec.split(':')[0]
			val_type = sec.split('(')[-1].split(')')[0]
			fixed_type = val_type.replace('*', '').strip()
			var = sec.split(')')[-1]

			log_string += ' ' + val_name + ((': ' + (reg_types[fixed_type] if fixed_type in reg_types else "%@")) if not (val_type == val_name == var) else '')
			if not val_type == val_name == var: 
				vars_string += ', '
				if val_type == 'SEL':
					vars_string += f'NSStringFromSelector({var})'
				elif '*' not in val_type or fixed_type not in reg_types:
					vars_string += var
				else:
					'*' + var

			if fixed_type not in reg_types and fixed_type not in bad_types and val_type != val_name and val_type[:2] not in base_prefixes:
				extra_types.add(fixed_type)

			if idclass and val_type == 'id':
				log_string += ' (class: %@)'
				vars_string += f', [{var} class]'

			sec = ''

	log_string += ' in ' + interface

	if ret_type != 'void':
		log_string += ' with a return of ' + reg_types[ret_type if ret_type in reg_types else 'id']
		vars_string += ', orig'
		if idclass and ret_type == 'id':
			log_string += ' (class: %@)'
			vars_string += ', [orig class]'

	log_string += f'"{vars_string}];'
	nslog = ''

	if no_newline:
		log_string += '\n\tlog = [[log stringByReplacingOccurrencesOfString:@"\\n" withString:@""] stringByTrimmingCharactersInSet:[NSCharacterSet newlineCharacterSet]];'

	if file:
		nslog = f'\t[log writeToFile:@"{file_location}" atomically:NO encoding:NSStringEncodingConversionAllowLossy error:nil];'
	else:
		nslog = '\tNSLog(@"%@", log);'

	return funcname + ' {\n' + orig_string + ('\n' if orig_string != '' else '') + log_string + '\n' + nslog + '\n' + ret_string + '\n}'

def together():
	ostr = ''
	with open(parse_location, 'r') as file:
		lines = file.readlines()
		interface = ''

		for i in lines:
			if i[:2] == '//':
				continue
			elif '@interface' in i:
				interface = i[i.index(' '):i.index(':')].strip()
				ostr += f'%hook {interface}\n\n'
				continue
			elif (i[:3] in ('- (', '+ (') or i[:2] in ('-(', '+(')) and interface != '':
				new_line = getLogString(i, interface)
				ostr += f'{new_line}\n\n'

	if interface != '': ostr += '%end\n'

	return ostr

def separated():
	hook_called = False
	ostr = ''

	with open(parse_location, 'r') as file:
		lines = file.readlines()
		lines.sort()
		interface = ''
		src = ''

		for line in lines:
			if len(line.strip()) == 0:
				continue

			past_src = src
			src = path.abspath(line[:line.find(':')])

			if interface == '' or src != past_src:
				with open(src, 'r') as src_file:
					src_lines = src_file.readlines()
					for src_line in src_lines:
						if '@interface' in src_line:
							first_part = src_line[src_line.find(' '):].lstrip()
							interface = first_part[:first_part.find(' ')]

				if hook_called: ostr += '%end\n\n'

			if interface == '': continue

			if src != past_src:
				ostr += f'%hook {interface}\n\n'
				hook_called = True

			substrings = line.split(':')
			funcname = ':'.join(substrings[2:])
			print_line = getLogString(funcname, interface)

			ostr += f'{print_line}\n\n'

	ostr += '\n%end'
	return ostr

def parseArgs():
	global help
	global no_newline
	global file
	global file_location
	global sep
	global prefix
	global no_newline
	global parse_location
	global idclass

	skip = False

	for n, a in enumerate(argv):
		if skip or len(a) < 2 or n == 0:
			skip = False
			continue
		if a[0] == '-' and a[1] != '-' and len(a) > 2:
			for c in a[1:]:
				if c == "s":
					sep = True
				elif c == "n":
					no_newline = True
				elif c == 'h':
					help = True
				elif c == 'c':
					idclass = True
		elif a in ('-s', '--sep'):
			sep = True
		elif a in ('-f', '--file'):
			file = True
			if argv[n+1][0] != '-' and argv[n+1][0] != '/' and n != len(argv) - 2:
				print(f'Please specify the absolute path of the file to log to after the \033[1m{a}\033[0m flag, e.g. "{a} /var/mobile/Documents/nlgf.log"')
				exit()
			elif argv[n+1][0] == '/' and n != len(argv) - 2:
				file_location = argv[n+1]
				skip = True
		elif a in ('-n', '--newline'):
			no_newline = True
		elif a in ('-h', '--help'):
			help = True
		elif a in ('-p', '--prefix'):
			if n == len(argv) - 2:
				print(f'Please give a string to use as the prefix if you do invoke the \033[1m{a}\033[0m flag')
				exit()
			else:
				prefix = argv[n+1]
				skip = True
		elif a in ('-c', '--class'):
			idclass = True
		elif n == len(argv) - 1:
			parse_location = a
		else:
			print(f'Unrecognized option \033[1m{a}\033[0m. Exiting...')
			exit()

def printHelp():
	help_msg = '''
	Usage: python3 ./log.py <options> /path/to/header/file.h

	\033[1mOptions:\033[0m
	    -h, --help    : Prints this help message and ignores all other options
	    -s, --sep     : Parses a file as a list of functions from different files, as opposed to a file with one interface
	                    and multiple methods/properties listed for that interface.
	    -n, --newline : Removes newlines from the log string so that everything is on one line and will work well
	                    with programs like grep when parsing output
	    -f, --file    : Logs output to a specific file instead of NSLog. You can specify a file location to log to by specifying
	                    a file location after this, e.g. \033[1m-f /var/mobile/log.txt\033[0m ; if you use this flag but don't specify a location, 
	                    output will be logged to \033[1m/var/mobile/Documents/nslog.log\033[0m
	    -c, --class   : Will print the class each time it logs an object of type \033[1mid\033[0m
	    -p, --prefix  : Allows you to specify a custom prefix, passed in directly after this flag (e.g. \033[1m-p "MYLOG"\033[0m ; without this flag, everything
	                    will be logged with the prefix "NSLG"
	'''

	print(help_msg)
	exit()

def main():
	global help
	parseArgs()

	if help:
		printHelp()

	ostr = separated() if sep else together()
	for i in extra_types:
		print(f'@interface {i}\n@end\n')

	print(ostr)

if __name__ == '__main__':
	main()
