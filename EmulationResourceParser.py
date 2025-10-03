#!/bin/env python3

import subprocess
import re
from collections import defaultdict
from datetime import datetime


class Domain:
    """Represents a single domain resource."""
    
    def __init__(self, board, domain, owner, pid, t_pod, design, elapsed_time, reserved_key):
        self.board = board
        self.domain = domain
        self.owner = owner
        self.pid = pid
        self.t_pod = t_pod
        self.design = design
        self.elapsed_time = elapsed_time
        self.reserved_key = reserved_key
        self.is_free = (owner == 'NONE')
    
    def get_full_id(self):
        """Returns the full domain identifier (e.g., '0.0')."""
        return "{}.{}".format(self.board, self.domain)


class Board:
    """Represents a board with multiple domains."""
    
    def __init__(self, board_id, cluster_id, status):
        self.board_id = board_id
        self.cluster_id = cluster_id
        self.status = status
        self.domains = []
    
    def add_domain(self, domain):
        """Adds a domain to this board."""
        self.domains.append(domain)
    
    def get_free_domains(self):
        """Returns list of free domains on this board."""
        return [d for d in self.domains if d.is_free]
    
    def get_used_domains(self):
        """Returns list of used domains on this board."""
        return [d for d in self.domains if not d.is_free]


class EmulatorResourceParser:
    """Parses test_server output to track emulator resource allocation."""
    
    def __init__(self):
        self.emulator_name = None
        self.hardware = None
        self.configmgr = None
        self.system_status = None
        self.boards = []
        self.raw_output = ""
        self.timestamp = None
        
    def run_command(self, command="test_server"):
        """
        Runs the specified command and parses the output.
        
        Args:
            command: Command to execute (default: "test_server")
        """
        try:
            # Capture timestamp when command is run
            self.timestamp = datetime.now().isoformat()
            
            # Python 3.6 compatible subprocess call
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = proc.communicate(timeout=30)
            self.raw_output = stdout
            self.parse_output(self.raw_output)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("Command '{}' timed out".format(command))
        except Exception as e:
            raise RuntimeError("Failed to run command '{}': {}".format(command, e))
    
    def parse_output(self, output):
        """
        Parses the test_server output.
        
        Args:
            output: Raw output string from test_server command
        """
        # Set timestamp if not already set (for when parsing without running command)
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
            
        self.boards = []
        lines = output.strip().split('\n')
        
        # Parse header
        if lines:
            header = lines[0]
            self._parse_header(header)
        
        current_cluster = None
        current_board = None
        
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
                
            # Parse cluster info
            if line.startswith('Cluster'):
                match = re.match(r'Cluster (\d+) has \d+ boards\s+CCD: (\w+)', line)
                if match:
                    current_cluster = int(match.group(1))
                    
            # Parse board info
            elif line.startswith('Board') and 'has' in line and 'domains' in line:
                match = re.match(r'Board\s+(\d+) has\s+\d+ domains\s+Board: (\w+)', line)
                if match:
                    board_id = int(match.group(1))
                    board_status = match.group(2)
                    current_board = Board(board_id, current_cluster, board_status)
                    self.boards.append(current_board)
                    
            # Parse domain info
            elif line.startswith('Domain') or (len(line) >= 5 and '.' in line[:5]):
                # Skip header line
                if 'Owner' in line and 'PID' in line:
                    continue
                    
                # Parse domain data
                parts = line.split()
                if len(parts) >= 8 and current_board is not None:
                    try:
                        domain_id = parts[0]
                        if '.' in domain_id:
                            board_num, domain_num = map(int, domain_id.split('.'))
                            owner = parts[1]
                            pid = parts[2]
                            t_pod = parts[5] if parts[5] != '--' else ''
                            design = parts[6]
                            elapsed_time = parts[7] if len(parts) > 7 else '--'
                            reserved_key = parts[8] if len(parts) > 8 else '--'
                            
                            domain = Domain(
                                board_num,
                                domain_num,
                                owner,
                                pid,
                                t_pod,
                                design,
                                elapsed_time,
                                reserved_key
                            )
                            current_board.add_domain(domain)
                    except (ValueError, IndexError):
                        continue
    
    def _parse_header(self, header):
        """Parses the header line for system information."""
        emulator_match = re.search(r'Emulator:\s*(\S+)', header)
        hardware_match = re.search(r'Hardware:\s*([\w\s]+?)(?=Configmgr:|$)', header)
        configmgr_match = re.search(r'Configmgr:\s*(\S+)', header)
        status_match = re.search(r'System Status:\s*(\w+)', header)
        
        self.emulator_name = emulator_match.group(1) if emulator_match else None
        self.hardware = hardware_match.group(1).strip() if hardware_match else None
        self.configmgr = configmgr_match.group(1) if configmgr_match else None
        self.system_status = status_match.group(1) if status_match else None
    
    def get_free_domains(self, cluster=None):
        """
        Returns all free domains across all boards.
        
        Args:
            cluster: Optional cluster ID to filter domains (None returns all clusters)
        """
        free = []
        for board in self.boards:
            if cluster is None or board.cluster_id == cluster:
                free.extend(board.get_free_domains())
        return free
    
    def get_used_domains(self, cluster=None):
        """
        Returns all used domains across all boards.
        
        Args:
            cluster: Optional cluster ID to filter domains (None returns all clusters)
        """
        used = []
        for board in self.boards:
            if cluster is None or board.cluster_id == cluster:
                used.extend(board.get_used_domains())
        return used
    
    def get_domains_by_user(self):
        """Returns dictionary mapping usernames to their allocated domains."""
        user_domains = defaultdict(list)
        for board in self.boards:
            for domain in board.get_used_domains():
                user_domains[domain.owner].append(domain)
        return dict(user_domains)
    
    def get_board(self, board_id):
        """Returns a specific board by ID."""
        for board in self.boards:
            if board.board_id == board_id:
                return board
        return None
    
    def get_resource_summary(self):
        """Returns a summary of resource utilization."""
        total_domains = sum(len(b.domains) for b in self.boards)
        free_domains = len(self.get_free_domains())
        used_domains = len(self.get_used_domains())
        
        return {
            'emulator': self.emulator_name,
            'hardware': self.hardware,
            'system_status': self.system_status,
            'total_boards': len(self.boards),
            'total_domains': total_domains,
            'free_domains': free_domains,
            'used_domains': used_domains,
            'utilization_percent': (used_domains / total_domains * 100) if total_domains > 0 else 0,
            'users': list(self.get_domains_by_user().keys())
        }
    
    def print_summary(self):
        """Prints a formatted summary of resource allocation."""
        summary = self.get_resource_summary()
        
        print("Timestamp: {}".format(self.timestamp))
        print("Emulator: {}".format(summary['emulator']))
        print("Hardware: {}".format(summary['hardware']))
        print("System Status: {}".format(summary['system_status']))
        print("\nResource Summary:")
        print("  Total Boards: {}".format(summary['total_boards']))
        print("  Total Domains: {}".format(summary['total_domains']))
        print("  Used Domains: {}".format(summary['used_domains']))
        print("  Free Domains: {}".format(summary['free_domains']))
        print("  Utilization: {:.1f}%".format(summary['utilization_percent']))
        print("\nActive Users: {}".format(', '.join(summary['users'])))
        
        print("\nDomains by User:")
        for user, domains in self.get_domains_by_user().items():
            print("  {}: {} domains".format(user, len(domains)))
    
    def get_json_summary(self):
        """Returns the summary data in JSON-serializable format."""
        import json
        
        summary = self.get_resource_summary()
        
        # Add detailed domain information by user
        domains_by_user = {}
        for user, domains in self.get_domains_by_user().items():
            domains_by_user[user] = {
                'domain_count': len(domains),
                'domains': [
                    {
                        'id': domain.get_full_id(),
                        'board': domain.board,
                        'domain': domain.domain,
                        'pid': domain.pid,
                        't_pod': domain.t_pod,
                        'design': domain.design,
                        'elapsed_time': domain.elapsed_time,
                        'reserved_key': domain.reserved_key
                    }
                    for domain in domains
                ]
            }
        
        # Add free domains information
        free_domains_list = [
            {
                'id': domain.get_full_id(),
                'board': domain.board,
                'domain': domain.domain
            }
            for domain in self.get_free_domains()
        ]
        
        # Build complete JSON structure
        json_data = {
            'timestamp': self.timestamp,
            'emulator': summary['emulator'],
            'hardware': summary['hardware'],
            'configmgr': self.configmgr,
            'system_status': summary['system_status'],
            'resource_summary': {
                'total_boards': summary['total_boards'],
                'total_domains': summary['total_domains'],
                'used_domains': summary['used_domains'],
                'free_domains': summary['free_domains'],
                'utilization_percent': round(summary['utilization_percent'], 2)
            },
            'domains_by_user': domains_by_user,
            'free_domains': free_domains_list
        }
        
        return json.dumps(json_data, indent=2)
    
    def print_json_summary(self):
        """Prints the summary data in JSON format."""
        print(self.get_json_summary())


# Example usage
if __name__ == "__main__":
    parser = EmulatorResourceParser()
    
    parser.run_command("test_server")
    
    # Print summary
    parser.print_json_summary()
    
    # Access specific information
    print("\n\nFree domains:")
    for domain in parser.get_free_domains():
        print("  {}".format(domain.get_full_id()))
